SELECT DISTINCT i.game_id
FROM nba.game_inactives i
ANTI JOIN nba.games g USING (game_id)
