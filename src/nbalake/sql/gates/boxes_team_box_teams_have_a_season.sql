SELECT DISTINCT b.season, b.team_id
FROM nba.team_box b
ANTI JOIN nba.team_seasons t ON t.season = b.season AND t.team_id = b.team_id
