SELECT game_id, count(*) AS n FROM nba.games GROUP BY game_id HAVING count(*) > 1
