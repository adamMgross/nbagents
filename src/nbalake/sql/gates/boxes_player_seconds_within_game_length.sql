SELECT p.game_id, p.team_id, p.player_id, p.seconds, t.seconds AS team_seconds
FROM nba.player_box p
JOIN nba.team_box t USING (game_id, team_id)
WHERE p.seconds > t.seconds / 5 + 60
