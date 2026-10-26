SELECT arena, team_id, count(*) AS n
FROM nba.arenas
GROUP BY ALL
HAVING count(*) > 1
