SELECT season, player_id, count(*) AS n
FROM nba.draft_combine
GROUP BY ALL
HAVING count(*) > 1
