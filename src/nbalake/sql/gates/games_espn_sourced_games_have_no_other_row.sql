SELECT e.game_id, g.game_id AS other_game_id
FROM nba.games e
JOIN nba.games g
  ON g.game_id <> e.game_id
 AND (g.espn_game_id = e.espn_game_id
      OR (g.game_date = e.game_date AND g.home_team_id = e.home_team_id AND g.away_team_id = e.away_team_id))
WHERE e.source = 'espn'
