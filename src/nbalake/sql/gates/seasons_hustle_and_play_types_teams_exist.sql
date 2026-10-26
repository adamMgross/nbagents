SELECT 'team_season_hustle' AS table_name, h.team_id
FROM nba.team_season_hustle h ANTI JOIN nba.teams t USING (team_id)
UNION ALL
SELECT 'player_season_hustle', h.last_team_id
FROM nba.player_season_hustle h ANTI JOIN nba.teams t ON t.team_id = h.last_team_id
UNION ALL
SELECT 'player_season_play_types', p.team_id
FROM nba.player_season_play_types p ANTI JOIN nba.teams t USING (team_id)
