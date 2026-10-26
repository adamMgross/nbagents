SELECT DISTINCT m.game_id
FROM nba.matchups_game m
ANTI JOIN nba.games g USING (game_id)
