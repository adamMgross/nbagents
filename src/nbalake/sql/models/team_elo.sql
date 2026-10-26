WITH RECURSIVE
overlap AS (
    SELECT max(year_id)::INTEGER AS season FROM fte.elo
),
played AS (
    SELECT g.game_id, g.season, g.game_date, g.home_team_id, g.away_team_id,
           g.home_pts, g.away_pts, g.neutral_site
    FROM nba.games g, overlap o
    WHERE g.season >= o.season
      AND g.season_type IN ('regular', 'play-in', 'playoffs', 'nba-cup')
      AND g.home_team_id IS NOT NULL AND g.away_team_id IS NOT NULL
      AND g.home_pts IS NOT NULL AND g.away_pts IS NOT NULL
),
home_share AS (
    SELECT s.season, avg((h.home_pts > h.away_pts)::INTEGER) AS p
    FROM (SELECT DISTINCT season FROM played) s
    JOIN nba.games h ON h.season BETWEEN s.season - 3 AND s.season - 1
    WHERE NOT h.neutral_site
      AND h.season_type IN ('regular', 'play-in', 'playoffs', 'nba-cup')
      AND h.home_pts IS NOT NULL AND h.away_pts IS NOT NULL
    GROUP BY 1
),
edges AS (
    SELECT s.season, m.method,
           CASE m.method WHEN 'fte' THEN 100 ELSE coalesce(400 * log10(h.p / (1 - h.p)), 100) END AS edge
    FROM (SELECT DISTINCT season FROM played) s
    CROSS JOIN (VALUES ('fte'), ('fit')) m(method)
    LEFT JOIN home_share h USING (season)
),
days AS (
    SELECT game_date, season, row_number() OVER (ORDER BY game_date) AS day_no
    FROM (SELECT DISTINCT game_date, season FROM played)
),
sides AS (
    SELECT d.day_no, p.game_id, e.method, p.home_team_id AS team_id,
           p.home_pts - p.away_pts AS margin, CASE WHEN p.neutral_site THEN 0 ELSE e.edge END AS edge
    FROM played p JOIN days d USING (game_date) JOIN edges e ON e.season = p.season
    UNION ALL
    SELECT d.day_no, p.game_id, e.method, p.away_team_id,
           p.away_pts - p.home_pts, CASE WHEN p.neutral_site THEN 0 ELSE -e.edge END
    FROM played p JOIN days d USING (game_date) JOIN edges e ON e.season = p.season
),
seed AS (
    SELECT f.team_id, arg_max(e.elo_n, e.gameorder) AS elo
    FROM fte.elo e
    JOIN nba.franchises f ON f.code = e.team_id
    JOIN overlap o ON e.year_id = o.season - 1
    GROUP BY 1
),
ratings AS (
    SELECT t.team_id, m.method, o.season - 1 AS season, 0::BIGINT AS day_no, coalesce(s.elo, 1300) AS elo,
           NULL::VARCHAR AS game_id, NULL::DOUBLE AS elo_pre, NULL::DOUBLE AS win_prob,
           NULL::DOUBLE AS edge
    FROM (SELECT DISTINCT team_id FROM sides) t
    CROSS JOIN (VALUES ('fte'), ('fit')) m(method)
    CROSS JOIN overlap o
    LEFT JOIN seed s USING (team_id)
    UNION ALL
    SELECT team_id, method, season, day_no,
           CASE WHEN game_id IS NULL THEN carried
                ELSE carried + 20 * pow(abs(margin) + 3, 0.8) / (7.5 + 0.006 * sign(margin) * diff)
                     * ((margin > 0)::INTEGER - win_prob) END,
           game_id, carried, win_prob, edge
    FROM (
        SELECT *, 1 / (1 + pow(10, -diff / 400)) AS win_prob
        FROM (
            SELECT c.*, s.game_id, s.margin, s.edge,
                   c.carried + s.edge
                       - (sum(c.carried) OVER (PARTITION BY s.game_id, c.method) - c.carried) AS diff
            FROM (
                SELECT r.team_id, r.method, d.season, d.day_no,
                       CASE WHEN d.season > r.season THEN 0.75 * r.elo + 0.25 * 1505 ELSE r.elo END
                           AS carried
                FROM ratings r
                JOIN days d ON d.day_no = r.day_no + 1
            ) c
            LEFT JOIN sides s ON s.day_no = c.day_no AND s.team_id = c.team_id AND s.method = c.method
        )
    )
)
SELECT
    game_id,
    any_value(season) AS season,
    team_id,
    any_value(elo_pre) FILTER (WHERE method = 'fte') AS elo_pre,
    any_value(elo) FILTER (WHERE method = 'fte') AS elo_post,
    any_value(win_prob) FILTER (WHERE method = 'fte') AS win_prob,
    any_value(elo_pre) FILTER (WHERE method = 'fit') AS fit_pre,
    any_value(elo) FILTER (WHERE method = 'fit') AS fit_post,
    any_value(win_prob) FILTER (WHERE method = 'fit') AS fit_win_prob,
    any_value(edge) FILTER (WHERE method = 'fit') AS fit_edge
FROM ratings
WHERE game_id IS NOT NULL
GROUP BY game_id, team_id
