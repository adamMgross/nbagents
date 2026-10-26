SELECT * FROM nba.depth_charts WHERE snapshot_date = (SELECT max(snapshot_date) FROM nba.depth_charts)
