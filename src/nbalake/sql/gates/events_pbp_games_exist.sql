SELECT DISTINCT p.game_id FROM nba.pbp p ANTI JOIN nba.games g USING (game_id)
