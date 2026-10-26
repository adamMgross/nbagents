WITH counted AS (
    SELECT count(DISTINCT espn_game_id) AS games,
           count(DISTINCT espn_game_id) FILTER (game_id IS NULL) AS unresolved
    FROM nba.pbp_espn
)
SELECT unresolved, games FROM counted WHERE unresolved > 0.001 * games
