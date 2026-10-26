SELECT game_id, count(*) AS n FROM nba.team_box GROUP BY game_id HAVING count(*) <> 2
