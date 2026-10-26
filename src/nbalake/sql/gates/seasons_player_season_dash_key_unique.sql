SELECT season, season_type, player_id, count(*) AS n
FROM nba.player_season_dash
GROUP BY ALL
HAVING count(*) > 1
