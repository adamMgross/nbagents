SELECT game_id, off_player_id, def_player_id, count(*) AS n
FROM nba.matchups_game
GROUP BY ALL
HAVING count(*) > 1
