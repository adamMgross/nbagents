WITH bands AS (
    SELECT season, season_type, player_id, sum(fga) AS bands
    FROM nba.player_season_closest_defender
    GROUP BY ALL
)
SELECT b.season, b.season_type, b.player_id, b.bands, d.fga
FROM bands b
JOIN nba.player_season_dash d USING (season, season_type, player_id)
WHERE d.fga >= 200 AND abs(b.bands - d.fga) > 0.1 * d.fga
