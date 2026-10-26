WITH team AS (
    SELECT game_id, team_id, pts, source FROM nba.team_box
),
players AS (
    SELECT game_id, team_id, sum(pts) AS pts, count(*) FILTER (player_id IS NULL) AS unresolved
    FROM nba.player_box
    GROUP BY ALL
),
listed AS (
    SELECT * FROM nba.games g
    WHERE g.source = 'nba' OR g.espn_game_id IS NOT NULL
       OR (g.season_type IN ('regular', 'playoffs') AND g.season >= (SELECT min(season) FROM nba.team_box))
),
sides AS (
    SELECT g.game_id, g.season, g.season_type, 'home' AS side, g.home_team_id AS team_id, g.home_pts AS schedule_pts
    FROM listed g
    UNION ALL
    SELECT g.game_id, g.season, g.season_type, 'away', g.away_team_id, g.away_pts
    FROM listed g
)
SELECT
    s.game_id, s.season, s.season_type, s.side, s.team_id,
    t.source,
    s.schedule_pts,
    t.pts AS team_box_pts,
    p.pts AS player_sum_pts,
    p.unresolved AS unresolved_players,
    t.game_id IS NULL AS team_box_missing,
    t.pts IS DISTINCT FROM s.schedule_pts AS team_box_differs,
    CASE WHEN t.game_id IS NULL THEN p.pts IS NOT NULL AND p.pts <> s.schedule_pts
         ELSE p.pts IS DISTINCT FROM t.pts END AS player_sum_differs
FROM sides s
LEFT JOIN team t ON t.game_id = s.game_id AND t.team_id = s.team_id
LEFT JOIN players p ON p.game_id = s.game_id AND p.team_id = s.team_id
WHERE t.game_id IS NULL OR t.pts IS DISTINCT FROM s.schedule_pts OR p.pts IS DISTINCT FROM t.pts
   OR p.unresolved > 0
