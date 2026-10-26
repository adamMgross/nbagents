WITH nba_games AS (
    SELECT
        game_id,
        season::INTEGER AS season,
        CASE season_type WHEN 'regular-season' THEN 'regular' ELSE season_type END AS season_type,
        'NBA' AS lg,
        CAST(game_date AS DATE) AS game_date,
        nullif(home_team_id, 0) AS home_team_id,
        nullif(away_team_id, 0) AS away_team_id,
        home_pts::INTEGER AS home_pts,
        away_pts::INTEGER AS away_pts
    FROM sdv.nba_stats_schedules
    WHERE (home_team_id <> 0 OR away_team_id <> 0)
      AND NOT (season_type IN ('regular-season', 'playoffs', 'play-in', 'nba-cup')
               AND home_pts = 0 AND away_pts = 0)
),
fte_games AS (
    SELECT
        e.game_id AS fte_game_id,
        e.year_id::INTEGER AS season,
        CASE WHEN e.is_playoffs = 1 THEN 'playoffs' ELSE 'regular' END AS season_type,
        CASE WHEN e.lg_id = 'NBA' AND e.year_id < 1950 THEN 'BAA' ELSE e.lg_id END AS lg,
        CAST(e.date_game AS DATE) AS game_date,
        h.team_id AS home_team_id,
        a.team_id AS away_team_id,
        CASE WHEN e.swapped THEN e.opp_pts ELSE e.pts END::INTEGER AS home_pts,
        CASE WHEN e.swapped THEN e.pts ELSE e.opp_pts END::INTEGER AS away_pts,
        e.game_location = 'N' AS neutral_site
    FROM (
        SELECT *, game_location = 'N' AND right(game_id, 3) = opp_id AS swapped
        FROM fte.elo
        WHERE _iscopy = 0
    ) e
    JOIN nba.franchises h ON h.code = CASE WHEN e.swapped THEN e.opp_id ELSE e.team_id END
    JOIN nba.franchises a ON a.code = CASE WHEN e.swapped THEN e.team_id ELSE e.opp_id END
),
fte_by_date AS (
    SELECT n.game_id, f.fte_game_id, f.neutral_site
    FROM nba_games n
    JOIN fte_games f
      ON f.game_date = n.game_date AND f.home_team_id = n.home_team_id AND f.away_team_id = n.away_team_id
),
fte_by_score AS (
    SELECT n.game_id, f.fte_game_id, f.neutral_site
    FROM nba_games n
    JOIN fte_games f
      ON f.season = n.season AND f.season_type = n.season_type
     AND f.home_team_id = n.home_team_id AND f.away_team_id = n.away_team_id
     AND f.home_pts = n.home_pts AND f.away_pts = n.away_pts
    WHERE n.game_id NOT IN (SELECT game_id FROM fte_by_date)
      AND f.fte_game_id NOT IN (SELECT fte_game_id FROM fte_by_date)
    QUALIFY count(*) OVER (PARTITION BY n.game_id) = 1 AND count(*) OVER (PARTITION BY f.fte_game_id) = 1
),
espn AS (
    SELECT
        id AS espn_game_id,
        CAST(timezone('America/New_York', CAST(date AS TIMESTAMPTZ)) AS DATE) AS game_date,
        home_id, away_id, home_score, away_score, neutral_site,
        attendance::INTEGER AS attendance, venue_full_name AS venue,
        status_type_completed AS completed,
        CASE WHEN type_abbreviation = 'ALLSTAR' THEN 'all-star'
             WHEN type_abbreviation = 'CC' THEN 'nba-cup'
             ELSE CASE season_type WHEN 1 THEN 'preseason' WHEN 2 THEN 'regular'
                                   WHEN 3 THEN 'playoffs' WHEN 5 THEN 'play-in' END
        END AS season_type
    FROM sdv.espn_nba_schedule_master
    QUALIFY row_number() OVER (PARTITION BY id ORDER BY status_type_completed DESC NULLS LAST, attendance DESC NULLS LAST) = 1
),
espn_teams AS (
    SELECT e.*, h.team_id AS home_team_id, a.team_id AS away_team_id, h.season
    FROM espn e
    JOIN nba.team_seasons h ON h.espn_team_id = e.home_id
    JOIN nba.team_seasons a ON a.espn_team_id = e.away_id AND a.season = h.season
    WHERE e.game_date BETWEEN make_date(h.season - 1, 7, 1) AND make_date(h.season, 6, 30)
),
crosswalk AS (
    SELECT DISTINCT nba_game_id AS game_id, TRY_CAST(espn_game_id AS INTEGER) AS espn_game_id
    FROM sdv.nba_schedule_crosswalk
    WHERE nba_game_id IS NOT NULL AND TRY_CAST(espn_game_id AS INTEGER) IS NOT NULL
    QUALIFY count(*) OVER (PARTITION BY nba_game_id) = 1
),
canonical AS (
    SELECT n.*, m.fte_game_id, coalesce(m.neutral_site, false) AS fte_neutral, 'nba' AS source
    FROM nba_games n
    LEFT JOIN (SELECT * FROM fte_by_date UNION ALL SELECT * FROM fte_by_score) m USING (game_id)
    UNION ALL
    SELECT fte_game_id, season, season_type, lg, game_date, home_team_id, away_team_id,
           home_pts, away_pts, fte_game_id, neutral_site, 'fte'
    FROM fte_games
    WHERE season < 1997
),
espn_ids AS (
    SELECT game_id, espn_game_id
    FROM (
        SELECT u.game_id,
               CASE WHEN ce.completed = false THEN coalesce(d.espn_game_id, x.espn_game_id, c.espn_game_id)
                    ELSE coalesce(c.espn_game_id, d.espn_game_id, x.espn_game_id) END AS espn_game_id,
               coalesce(d.home_score + d.away_score, 1) > 0 AS scored
        FROM canonical u
        LEFT JOIN crosswalk c ON c.game_id = u.game_id
        LEFT JOIN espn ce ON ce.espn_game_id = c.espn_game_id
        LEFT JOIN espn_teams d
          ON (c.espn_game_id IS NULL OR ce.completed = false) AND d.game_date = u.game_date
         AND d.home_team_id = u.home_team_id AND d.away_team_id = u.away_team_id
        LEFT JOIN espn x
          ON c.espn_game_id IS NULL AND u.season_type = 'all-star' AND x.season_type = 'all-star'
         AND x.game_date = u.game_date AND x.home_score = u.home_pts AND x.away_score = u.away_pts
        QUALIFY scored = max(scored) OVER (PARTITION BY u.game_id)
    )
    QUALIFY count(*) OVER (PARTITION BY game_id) = 1
),
frontier AS (
    SELECT max(game_date) AS game_date FROM nba_games
),
unioned AS (
    SELECT u.*, i.espn_game_id
    FROM canonical u
    LEFT JOIN espn_ids i USING (game_id)
    UNION ALL
    SELECT 'espn' || d.espn_game_id::VARCHAR, d.season, d.season_type, 'NBA', d.game_date,
           d.home_team_id, d.away_team_id, d.home_score::INTEGER, d.away_score::INTEGER,
           NULL, false, 'espn', d.espn_game_id
    FROM espn_teams d, frontier f
    WHERE d.completed AND d.game_date > f.game_date AND d.season_type IS NOT NULL
      AND d.home_score + d.away_score > 0
)
SELECT
    u.game_id,
    u.season,
    u.season_type,
    u.lg,
    u.game_date,
    u.home_team_id,
    u.away_team_id,
    hs.name AS home_team_name,
    vs.name AS away_team_name,
    u.home_pts,
    u.away_pts,
    CASE WHEN u.home_pts > u.away_pts THEN u.home_team_id
         WHEN u.away_pts > u.home_pts THEN u.away_team_id END AS winner_team_id,
    coalesce(e.neutral_site, u.fte_neutral)
        OR coalesce(e.venue = 'ESPN Wide World of Sports Complex', false) AS neutral_site,
    e.attendance,
    e.venue,
    u.espn_game_id,
    u.fte_game_id,
    u.source
FROM unioned u
LEFT JOIN espn e ON e.espn_game_id = u.espn_game_id
LEFT JOIN nba.team_seasons hs ON hs.team_id = u.home_team_id AND hs.season = u.season
LEFT JOIN nba.team_seasons vs ON vs.team_id = u.away_team_id AND vs.season = u.season
