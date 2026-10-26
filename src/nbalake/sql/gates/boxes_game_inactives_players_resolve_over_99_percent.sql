WITH counted AS (
    SELECT
        count(*) FILTER (WHERE p.player_id IS NULL) AS unresolved,
        count(*) AS inactives
    FROM nba.game_inactives i
    LEFT JOIN nba.players p USING (player_id)
)
SELECT unresolved, inactives FROM counted WHERE unresolved > 0.01 * inactives
