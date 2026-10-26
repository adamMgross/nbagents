SELECT games, within_a_point
FROM (
    SELECT count(*) AS games, avg((abs(k.home_spread - e.home_spread) <= 1)::INTEGER) AS within_a_point
    FROM nba.game_lines k
    JOIN nba.game_lines e ON e.game_id = k.game_id AND e.source = 'espn'
    WHERE k.source = 'kaggle_lines'
)
WHERE games > 0 AND within_a_point < 0.90
