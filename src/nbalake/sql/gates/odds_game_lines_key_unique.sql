SELECT game_id, source, book, count(*) AS n
FROM nba.game_lines
GROUP BY ALL
HAVING count(*) > 1
