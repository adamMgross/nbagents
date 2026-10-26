SELECT snapshot_date, espn_team_id, position, depth_rank, count(*) AS n
FROM nba.depth_charts
GROUP BY ALL
HAVING count(*) > 1
