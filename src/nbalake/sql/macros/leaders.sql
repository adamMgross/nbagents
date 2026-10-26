-- The top players on one nba.player_seasons column, one row per player with traded players' season totals, over min_games. per_game divides by games. lg NULL means NBA and BAA, not ABA.
-- example: from leaders('pts', 2016, per_game := true) limit 10
CREATE OR REPLACE TEMP MACRO leaders(stat, season, min_games := 58, per_game := false, lg := NULL) AS TABLE
WITH args AS (
    SELECT season AS season, min_games AS min_games, per_game AS per_game, lg AS lg
),
picked AS (
    SELECT ps.*, a.per_game AS _per_game
    FROM args a
    JOIN nba.player_seasons ps ON ps.season = a.season AND ps.g >= a.min_games
    WHERE (a.lg IS NULL AND ps.lg IN ('NBA', 'BAA')) OR ps.lg = a.lg
    QUALIFY ps.multi_team OR count(*) OVER (PARTITION BY ps.season, ps.lg, ps.player_id) = 1
),
valued AS (
    SELECT s.player_id, s.player, s.bref_team, s.g,
        CASE WHEN s._per_game THEN COLUMNS('^' || stat || '$') / s.g
             ELSE COLUMNS('^' || stat || '$') END AS value
    FROM picked s
)
SELECT rank() OVER (ORDER BY v.value DESC) AS rank, v.player_id, v.player,
    v.bref_team AS team, v.g, v.value
FROM valued v
WHERE v.value IS NOT NULL
ORDER BY v.value DESC, v.player;
