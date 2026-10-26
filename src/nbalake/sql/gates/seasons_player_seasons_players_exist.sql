SELECT DISTINCT s.player_id FROM nba.player_seasons s ANTI JOIN nba.players p USING (player_id)
