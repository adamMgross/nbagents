SELECT snapshot_date, espn_athlete_id, count(*) AS n FROM nba.injuries GROUP BY ALL HAVING count(*) > 1
