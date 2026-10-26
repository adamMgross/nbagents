SELECT game_id, team_id, count(*) AS n
FROM nba.team_elo
GROUP BY ALL
HAVING count(*) > 1
