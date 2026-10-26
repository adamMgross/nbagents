SELECT game_id, official_id, count(*) AS n
FROM nba.game_officials
GROUP BY game_id, official_id
HAVING count(*) > 1
