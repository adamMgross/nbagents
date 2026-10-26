SELECT unresolved, total
FROM (SELECT count(*) FILTER (player_id IS NULL) AS unresolved, count(*) AS total FROM nba.awards)
WHERE unresolved > 0.001 * total
