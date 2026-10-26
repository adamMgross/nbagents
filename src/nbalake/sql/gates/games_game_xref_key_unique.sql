SELECT source, source_id, count(*) AS n FROM nba.game_xref GROUP BY ALL HAVING count(*) > 1
