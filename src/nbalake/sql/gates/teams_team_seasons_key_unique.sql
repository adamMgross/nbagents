SELECT season, team_id, count(*) AS n FROM nba.team_seasons GROUP BY ALL HAVING count(*) > 1
