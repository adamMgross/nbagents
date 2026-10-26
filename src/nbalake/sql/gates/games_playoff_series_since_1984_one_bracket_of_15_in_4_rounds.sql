WITH seasons AS (
    SELECT DISTINCT season FROM nba.games
    WHERE season >= 1984 AND season_type = 'playoffs' AND lg = 'NBA' AND winner_team_id IS NOT NULL
)
SELECT s.season, count(p.series_id) AS series, max(p.round) AS rounds,
       count(p.series_id) FILTER (WHERE p.next_series_id IS NULL) AS finals,
       count(DISTINCT p.round || '-' || p.best_of) - count(DISTINCT p.round) AS mixed_formats
FROM seasons s
LEFT JOIN nba.playoff_series p ON p.season = s.season AND p.lg = 'NBA'
GROUP BY 1
HAVING count(p.series_id) FILTER (WHERE p.winner_team_id IS NULL) = 0
   AND (count(p.series_id) <> 15 OR max(p.round) <> 4
        OR count(p.series_id) FILTER (WHERE p.next_series_id IS NULL) <> 1
        OR count(DISTINCT p.round || '-' || p.best_of) <> count(DISTINCT p.round))
