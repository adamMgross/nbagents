SELECT season, lg, team_id, count(*) AS n FROM nba.team_season_stats GROUP BY ALL HAVING count(*) > 1
