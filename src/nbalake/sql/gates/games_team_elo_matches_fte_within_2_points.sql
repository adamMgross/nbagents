SELECT l.game_id, l.team_id, l.elo_pre, e.elo_i AS fte_elo_pre
FROM nba.team_elo l
JOIN nba.games g USING (game_id)
JOIN nba.franchises f ON f.team_id = l.team_id
JOIN fte.elo e ON e.game_id = g.fte_game_id AND e.team_id = f.code
WHERE abs(l.elo_pre - e.elo_i) >= 2
