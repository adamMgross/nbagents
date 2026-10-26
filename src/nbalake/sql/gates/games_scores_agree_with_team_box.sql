SELECT g.game_id, g.home_pts, g.away_pts, hb.points AS home_box_pts, ab.points AS away_box_pts
FROM nba.games g
JOIN sdv.nba_stats_team_boxscores hb ON hb.game_id = g.game_id AND hb.team_id = g.home_team_id
JOIN sdv.nba_stats_team_boxscores ab ON ab.game_id = g.game_id AND ab.team_id = g.away_team_id
WHERE g.home_pts <> hb.points OR g.away_pts <> ab.points
