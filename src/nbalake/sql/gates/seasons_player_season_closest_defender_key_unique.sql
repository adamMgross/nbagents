SELECT season, season_type, player_id, defender_distance, count(*) AS n
FROM nba.player_season_closest_defender
GROUP BY ALL
HAVING count(*) > 1
