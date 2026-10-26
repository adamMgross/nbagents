SELECT 'injuries' AS source, snapshot_date, espn_team_id FROM nba.injuries WHERE team_id IS NULL
UNION ALL
SELECT 'depth_charts', snapshot_date, espn_team_id FROM nba.depth_charts WHERE team_id IS NULL
