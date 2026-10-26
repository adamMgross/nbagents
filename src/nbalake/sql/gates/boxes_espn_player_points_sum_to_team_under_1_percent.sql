SELECT differing, sides
FROM (
    SELECT
        (SELECT count(*) FROM nba.box_reconciliation WHERE source = 'espn' AND player_sum_differs) AS differing,
        (SELECT count(*) FROM nba.team_box WHERE source = 'espn') AS sides
)
WHERE differing > 0.01 * sides
