SELECT code, count(*) AS n FROM nba.franchises GROUP BY code HAVING count(*) > 1
