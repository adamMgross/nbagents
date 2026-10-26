SELECT DISTINCT p.player_id
FROM nba.player_box p
ANTI JOIN nba.players x USING (player_id)
WHERE p.source = 'nba'
