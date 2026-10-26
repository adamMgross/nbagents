WITH credited AS (
    SELECT game_id, assist_player_id AS player_id, 1 AS ast, 0 AS stl, 0 AS blk
    FROM nba.pbp_actors WHERE assist_player_id IS NOT NULL
    UNION ALL
    SELECT game_id, steal_player_id, 0, 1, 0 FROM nba.pbp_actors WHERE steal_player_id IS NOT NULL
    UNION ALL
    SELECT game_id, block_player_id, 0, 0, 1 FROM nba.pbp_actors WHERE block_player_id IS NOT NULL
),
pbp AS (
    SELECT game_id, player_id, sum(ast) AS ast, sum(stl) AS stl, sum(blk) AS blk
    FROM credited GROUP BY game_id, player_id
),
assisted_games AS (
    SELECT DISTINCT game_id FROM nba.pbp_actors WHERE assist_player_id IS NOT NULL
),
compared AS (
    SELECT
        (ag.game_id IS NOT NULL AND coalesce(p.ast, 0) <> b.ast)
            OR coalesce(p.stl, 0) <> b.stl
            OR coalesce(p.blk, 0) <> b.blk AS disagree
    FROM nba.player_box b
    LEFT JOIN pbp p USING (game_id, player_id)
    LEFT JOIN assisted_games ag USING (game_id)
    WHERE b.source = 'nba' AND b.game_id IN (SELECT game_id FROM nba.pbp_actors)
)
SELECT count(*) FILTER (WHERE disagree) AS disagree, count(*) AS player_games
FROM compared
HAVING count(*) FILTER (WHERE disagree) > 0.001 * count(*)
