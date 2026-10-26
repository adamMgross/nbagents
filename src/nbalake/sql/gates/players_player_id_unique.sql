SELECT player_id, count(*) AS n FROM nba.players GROUP BY player_id HAVING count(*) > 1
