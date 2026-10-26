SELECT DISTINCT o.game_id
FROM nba.game_officials o
ANTI JOIN nba.games g USING (game_id)
