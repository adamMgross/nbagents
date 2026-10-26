SELECT team_id, count(*) AS n FROM nba.teams GROUP BY team_id HAVING count(*) > 1
