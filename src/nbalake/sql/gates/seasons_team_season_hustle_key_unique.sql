SELECT season, season_type, team_id, count(*) AS n
FROM nba.team_season_hustle
GROUP BY ALL
HAVING count(*) > 1
