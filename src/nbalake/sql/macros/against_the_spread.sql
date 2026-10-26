-- A team's record against the median closing spread in a season, split by home or away and favorite or underdog, with every subtotal. Lines exist from 2006-07.
-- example: from against_the_spread(1610612744, 2017)
CREATE OR REPLACE TEMP MACRO against_the_spread(team_id, season, season_type := 'regular') AS TABLE
WITH graded AS (
    SELECT
        CASE WHEN t.is_home THEN 'home' ELSE 'away' END AS venue,
        CASE WHEN t.spread < 0 THEN 'favorite' WHEN t.spread > 0 THEN 'underdog' ELSE 'pick' END
            AS role,
        t.ats, t.margin + t.spread AS vs_spread
    FROM team_games_of(team_id, season, season_type) t
    WHERE t.ats IS NOT NULL
)
SELECT
    coalesce(g.venue, 'all') AS venue,
    coalesce(g.role, 'all') AS role,
    count(*) AS games,
    count(*) FILTER (WHERE g.ats = 'cover') AS covers,
    count(*) FILTER (WHERE g.ats = 'loss') AS losses,
    count(*) FILTER (WHERE g.ats = 'push') AS pushes,
    count(*) FILTER (WHERE g.ats = 'cover')
        / nullif(count(*) FILTER (WHERE g.ats <> 'push'), 0) AS cover_rate,
    avg(g.vs_spread) AS avg_margin_vs_spread
FROM graded g
GROUP BY GROUPING SETS ((g.venue, g.role), (g.venue), (g.role), ())
ORDER BY venue, role;
