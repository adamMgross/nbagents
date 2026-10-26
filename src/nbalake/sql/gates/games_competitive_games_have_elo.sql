SELECT game_id, season, team_id
FROM nba.team_games
WHERE season_type IN ('regular', 'play-in', 'playoffs', 'nba-cup')
  AND pts IS NOT NULL AND opp_pts IS NOT NULL
  AND elo_pre IS NULL
