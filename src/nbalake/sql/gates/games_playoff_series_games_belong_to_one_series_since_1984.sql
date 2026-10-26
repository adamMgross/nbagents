WITH members AS (
    SELECT unnest(game_ids) AS game_id, series_id FROM nba.playoff_series WHERE season >= 1984
)
SELECT g.game_id, g.season, count(m.series_id) AS series
FROM nba.games g
LEFT JOIN members m USING (game_id)
WHERE g.season >= 1984 AND g.season_type = 'playoffs' AND g.winner_team_id IS NOT NULL
GROUP BY ALL
HAVING count(m.series_id) <> 1
