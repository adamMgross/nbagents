SELECT decision, count(*) AS n
FROM nba.l2m_calls
WHERE decision NOT IN ('CC', 'IC', 'CNC', 'INC')
GROUP BY decision
