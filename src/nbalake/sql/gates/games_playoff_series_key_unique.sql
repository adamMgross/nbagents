SELECT series_id, count(*) AS n
FROM nba.playoff_series
GROUP BY 1
HAVING count(*) > 1
