WITH counted AS (
    SELECT count(*) FILTER (WHERE p.player_id IS NULL) AS unresolved, count(*) AS player_seasons
    FROM nba.player_impact i
    LEFT JOIN nba.players p USING (player_id)
)
SELECT unresolved, player_seasons FROM counted WHERE unresolved > 0.01 * player_seasons
