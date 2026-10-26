SELECT resolved, listed
FROM (
    SELECT count(player_id) AS resolved, count(*) AS listed
    FROM (
        SELECT player_id FROM nba.injuries
        UNION ALL
        SELECT player_id FROM nba.depth_charts
    )
)
WHERE resolved < 0.85 * listed
