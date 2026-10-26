WITH feeders AS (
    SELECT next_series_id AS series_id, count(*) AS n
    FROM nba.playoff_series
    WHERE next_series_id IS NOT NULL
    GROUP BY 1
)
SELECT s.series_id, s.round, s.winner_team_id, n.series_id AS next_series_id, n.round AS next_round,
       f.n AS feeders
FROM nba.playoff_series s
LEFT JOIN nba.playoff_series n ON n.series_id = s.next_series_id
LEFT JOIN feeders f ON f.series_id = s.series_id
WHERE (s.next_series_id IS NOT NULL AND (
        n.series_id IS NULL OR n.season <> s.season OR n.lg <> s.lg OR n.round <> s.round + 1
        OR s.winner_team_id NOT IN (n.home_court_team_id, n.other_team_id)))
   OR f.n > 2
