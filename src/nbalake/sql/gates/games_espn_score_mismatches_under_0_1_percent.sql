SELECT mismatched, matched
FROM (
    SELECT
        (SELECT count(*) FROM nba.games_cross_source WHERE issue = 'espn_score_mismatch') AS mismatched,
        (SELECT count(*) FROM nba.games WHERE espn_game_id IS NOT NULL) AS matched
)
WHERE mismatched > 0.001 * matched
