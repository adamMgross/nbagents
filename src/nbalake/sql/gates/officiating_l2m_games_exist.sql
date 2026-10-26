SELECT DISTINCT c.game_id FROM nba.l2m_calls c ANTI JOIN nba.games g USING (game_id)
