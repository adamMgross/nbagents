SELECT * FROM nba.injuries WHERE snapshot_date = (SELECT max(snapshot_date) FROM nba.injuries)
