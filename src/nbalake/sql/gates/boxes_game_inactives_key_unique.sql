SELECT game_id, team_id, player_id, count(*) AS n
FROM nba.game_inactives
GROUP BY game_id, team_id, player_id
HAVING count(*) > 1
