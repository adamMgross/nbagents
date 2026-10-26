SELECT out_of_range, totals
FROM (
    SELECT
        count(*) FILTER (WHERE total NOT BETWEEN 150 AND 300) AS out_of_range,
        count(total) AS totals
    FROM nba.game_lines
)
WHERE out_of_range > 0.002 * totals
