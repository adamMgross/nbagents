-- Wins per 82 games that one point per 100 possessions of net rating buys each NBA season from 1974, the within-season slope of win percentage on net rating pooled over the seasons within half_window.
-- example: from wins_per_point() where season >= 2015
CREATE OR REPLACE TEMP MACRO wins_per_point(half_window := 2) AS TABLE
WITH args AS (
    SELECT CASE WHEN half_window >= 0 THEN half_window
                ELSE error('half_window must be 0 or more') END AS half_window
),
seasons AS (
    SELECT t.season, any_value(a.half_window) AS half_window,
           regr_sxy(t.w / (t.w + t.l), t.n_rtg) AS sxy, regr_sxx(t.w / (t.w + t.l), t.n_rtg) AS sxx
    FROM args a
    JOIN nba.team_seasons t ON t.lg = 'NBA' AND t.w + t.l > 0 AND t.n_rtg IS NOT NULL
    GROUP BY t.season
)
SELECT s.season, 82 * sum(o.sxy) / sum(o.sxx) AS wins_per_point
FROM seasons s
JOIN seasons o ON o.season BETWEEN s.season - s.half_window AND s.season + s.half_window
GROUP BY s.season
ORDER BY s.season
