SELECT source, source_id, count(*) AS n FROM nba.player_xref GROUP BY ALL HAVING count(*) > 1
