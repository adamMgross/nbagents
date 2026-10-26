WITH counted AS (
    SELECT count(*) FILTER (WHERE p.player_id IS NULL) AS unresolved, count(*) AS rows
    FROM nba.player_season_hustle s
    LEFT JOIN nba.players p USING (player_id)
)
SELECT unresolved, rows FROM counted WHERE unresolved > 0.01 * rows
