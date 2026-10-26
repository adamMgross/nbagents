WITH located AS (
    SELECT g.game_id,
           CASE WHEN g.neutral_site THEN v.latitude ELSE coalesce(ht.latitude, h.latitude) END AS latitude,
           CASE WHEN g.neutral_site THEN v.longitude ELSE coalesce(ht.longitude, h.longitude) END AS longitude
    FROM nba.games g
    LEFT JOIN nba.arenas v ON v.arena = g.venue AND v.team_id IS NULL
    LEFT JOIN nba.team_seasons s ON s.team_id = g.home_team_id AND s.season = g.season
    LEFT JOIN nba.arenas ht ON ht.arena = s.arena AND ht.team_id = g.home_team_id
    LEFT JOIN nba.arenas h ON h.arena = s.arena AND h.team_id IS NULL
),
sides AS (
    SELECT game_id, season, season_type, game_date, fte_game_id,
           home_team_id AS team_id, away_team_id AS opponent_team_id,
           home_team_name AS team_name, away_team_name AS opponent_name, true AS is_home,
           home_pts AS pts, away_pts AS opp_pts
    FROM nba.games
    UNION ALL
    SELECT game_id, season, season_type, game_date, fte_game_id,
           away_team_id, home_team_id, away_team_name, home_team_name, false, away_pts, home_pts
    FROM nba.games
),
elo AS (
    SELECT e.game_id AS fte_game_id, f.team_id, e.elo_i, e.elo_n, e.forecast
    FROM fte.elo e
    JOIN nba.franchises f ON f.code = e.team_id
),
flagged AS (
    SELECT s.*, s.season_type IN ('regular', 'play-in', 'playoffs', 'nba-cup') AS counts,
           l.latitude, l.longitude
    FROM sides s
    LEFT JOIN located l USING (game_id)
),
rested AS (
    SELECT
        *,
        date_diff('day', lag(game_date) OVER (PARTITION BY team_id, season, counts ORDER BY game_date, game_id), game_date) AS gap,
        lag(latitude) OVER (PARTITION BY team_id, season, counts ORDER BY game_date, game_id) AS prev_latitude,
        lag(longitude) OVER (PARTITION BY team_id, season, counts ORDER BY game_date, game_id) AS prev_longitude,
        count(*) OVER (
            PARTITION BY team_id, counts ORDER BY game_date
            RANGE BETWEEN INTERVAL 7 DAYS PRECEDING AND INTERVAL 1 DAY PRECEDING
        ) AS recent
    FROM flagged
)
SELECT
    r.game_id,
    r.season,
    r.season_type,
    r.game_date,
    r.team_id,
    r.opponent_team_id,
    r.team_name,
    r.opponent_name,
    r.is_home,
    r.pts,
    r.opp_pts,
    r.pts > r.opp_pts AS won,
    r.pts - r.opp_pts AS margin,
    coalesce(e.elo_i, l.elo_pre) AS elo_pre,
    coalesce(e.elo_n, l.elo_post) AS elo_post,
    coalesce(e.forecast, l.win_prob) AS elo_win_prob,
    CASE WHEN e.elo_i IS NOT NULL THEN 'fte' WHEN l.elo_pre IS NOT NULL THEN 'lake' END AS elo_source,
    l.fit_pre AS elo_fit_pre,
    l.fit_post AS elo_fit_post,
    l.fit_win_prob AS elo_fit_win_prob,
    CASE WHEN r.counts THEN r.gap END AS rest_days,
    CASE WHEN r.counts THEN r.gap = 1 END AS back_to_back,
    CASE WHEN r.counts THEN r.recent END AS games_last_7_days,
    CASE WHEN r.counts THEN 2 * 6371.0088 * asin(sqrt(
        pow(sin(radians(r.latitude - r.prev_latitude) / 2), 2)
        + cos(radians(r.prev_latitude)) * cos(radians(r.latitude))
          * pow(sin(radians(r.longitude - r.prev_longitude) / 2), 2)
    )) END AS travel_km,
    row_number() OVER (PARTITION BY r.team_id, r.season, r.season_type ORDER BY r.game_date, r.game_id) AS season_game_number
FROM rested r
LEFT JOIN elo e ON e.fte_game_id = r.fte_game_id AND e.team_id = r.team_id
LEFT JOIN nba.team_elo l ON l.game_id = r.game_id AND l.team_id = r.team_id
