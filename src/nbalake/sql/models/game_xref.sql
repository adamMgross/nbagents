SELECT 'nba' AS source, game_id AS source_id, game_id FROM nba.games WHERE source = 'nba'
UNION ALL
SELECT 'espn', espn_game_id::VARCHAR, game_id FROM nba.games WHERE espn_game_id IS NOT NULL
UNION ALL
SELECT 'fte', fte_game_id, game_id FROM nba.games WHERE fte_game_id IS NOT NULL
UNION ALL
SELECT 'minted', 'espn' || espn_game_id::VARCHAR, game_id FROM nba.games WHERE espn_game_id IS NOT NULL
