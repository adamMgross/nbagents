SELECT game_id, season
FROM nba.games
WHERE season_type IN ('regular', 'play-in', 'playoffs', 'nba-cup')
  AND home_pts = 0 AND away_pts = 0
