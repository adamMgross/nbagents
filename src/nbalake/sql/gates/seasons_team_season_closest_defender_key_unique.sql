SELECT season, season_type, team_id, side, defender_distance, count(*) AS n
FROM nba.team_season_closest_defender
GROUP BY ALL
HAVING count(*) > 1
