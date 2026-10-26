SELECT DISTINCT b.season, b.team_id
FROM sdv.nba_stats_team_boxscores b
ANTI JOIN nba.team_seasons t ON t.season = b.season AND t.team_id = b.team_id
WHERE b.team_id <> 0
