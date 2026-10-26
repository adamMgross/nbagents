SELECT player_id, source, count(*) AS n, string_agg(source_id, ',') AS source_ids
FROM nba.player_xref
WHERE source IN ('nba', 'bref')
GROUP BY ALL
HAVING count(*) > 1
