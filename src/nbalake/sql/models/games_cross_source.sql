WITH espn AS (
    SELECT
        id AS espn_game_id, season::INTEGER AS season,
        CAST(timezone('America/New_York', CAST(date AS TIMESTAMPTZ)) AS DATE) AS game_date,
        home_score, away_score, status_type_completed AS completed
    FROM sdv.espn_nba_schedule_master
    WHERE season_type IN (2, 3, 5) AND type_abbreviation <> 'ALLSTAR'
    QUALIFY row_number() OVER (PARTITION BY id ORDER BY status_type_completed DESC NULLS LAST) = 1
),
fte AS (
    SELECT game_id AS fte_game_id, year_id::INTEGER AS season, CAST(date_game AS DATE) AS game_date,
           CASE WHEN swapped THEN opp_pts ELSE pts END::INTEGER AS home_pts,
           CASE WHEN swapped THEN pts ELSE opp_pts END::INTEGER AS away_pts
    FROM (
        SELECT *, game_location = 'N' AND right(game_id, 3) = opp_id AS swapped
        FROM fte.elo
        WHERE _iscopy = 0
    )
)
SELECT 'nba_without_teams' AS issue, game_id, season::INTEGER AS season, game_id AS source_id,
       CAST(game_date AS DATE) AS game_date, season_type AS detail
FROM sdv.nba_stats_schedules
WHERE home_team_id = 0 AND away_team_id = 0
UNION ALL
SELECT 'fte_unmatched', NULL, f.season, f.fte_game_id, f.game_date, NULL
FROM fte f
ANTI JOIN nba.games g ON g.fte_game_id = f.fte_game_id
UNION ALL
SELECT 'espn_unmatched', NULL, e.season, e.espn_game_id::VARCHAR, e.game_date,
       CASE WHEN NOT e.completed THEN 'not completed'
            WHEN e.home_score + e.away_score = 0 THEN 'completed with a 0-0 placeholder score'
            ELSE 'completed' END
FROM espn e
ANTI JOIN nba.games g ON g.espn_game_id = e.espn_game_id
WHERE e.game_date <= (SELECT max(game_date) FROM nba.games)
UNION ALL
SELECT 'espn_score_mismatch', g.game_id, g.season, e.espn_game_id::VARCHAR, g.game_date,
       format('nba {}-{} espn {}-{}', g.home_pts, g.away_pts, e.home_score, e.away_score)
FROM nba.games g
JOIN espn e ON e.espn_game_id = g.espn_game_id
WHERE e.completed AND (g.home_pts <> e.home_score OR g.away_pts <> e.away_score)
UNION ALL
SELECT 'fte_score_mismatch', g.game_id, g.season, f.fte_game_id, g.game_date,
       format('nba {}-{} fte {}-{}', g.home_pts, g.away_pts, f.home_pts, f.away_pts)
FROM nba.games g
JOIN fte f ON f.fte_game_id = g.fte_game_id
WHERE g.source = 'nba' AND (g.home_pts <> f.home_pts OR g.away_pts <> f.away_pts)
