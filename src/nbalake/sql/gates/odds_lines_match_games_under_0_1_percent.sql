SELECT unmatched, total
FROM (
    SELECT
        (SELECT count(*) FROM odds.lines)
            - (SELECT count(*) FROM nba.game_lines WHERE source = 'kaggle_lines') AS unmatched,
        (SELECT count(*) FROM odds.lines) AS total
)
WHERE unmatched > 0.001 * total
