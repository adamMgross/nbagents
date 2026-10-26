SELECT g.game_id, g.season, t.team_id
FROM nba.games g, LATERAL (SELECT unnest([g.home_team_id, g.away_team_id]) AS team_id) t
ANTI JOIN nba.team_seasons s ON s.season = g.season AND s.team_id = t.team_id
WHERE g.season_type IN ('regular', 'play-in', 'playoffs', 'nba-cup')
