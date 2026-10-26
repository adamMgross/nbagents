SELECT unmatched, overlapping
FROM (
    SELECT
        (SELECT count(*) FROM nba.games_cross_source WHERE issue = 'fte_unmatched') AS unmatched,
        (SELECT count(*) FROM nba.games WHERE source = 'nba' AND fte_game_id IS NOT NULL) AS overlapping
)
WHERE unmatched > 0.001 * overlapping
