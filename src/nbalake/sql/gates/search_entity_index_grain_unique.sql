SELECT kind, id, label, count(*) AS n
FROM nba.entity_index
GROUP BY ALL
HAVING count(*) > 1
