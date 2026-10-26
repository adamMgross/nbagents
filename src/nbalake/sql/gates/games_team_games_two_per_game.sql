SELECT g.game_id, count(t.game_id) AS n
FROM nba.games g
LEFT JOIN nba.team_games t USING (game_id)
GROUP BY g.game_id
HAVING count(t.game_id) <> 2
