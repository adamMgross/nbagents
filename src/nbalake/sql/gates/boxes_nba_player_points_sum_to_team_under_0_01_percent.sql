SELECT differing, sides
FROM (
    SELECT
        (SELECT count(*) FROM nba.box_reconciliation WHERE source = 'nba' AND player_sum_differs) AS differing,
        (SELECT count(*) FROM nba.team_box WHERE source = 'nba') AS sides
)
WHERE differing > 0.0001 * sides
