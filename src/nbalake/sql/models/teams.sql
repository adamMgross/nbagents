WITH spans AS (
    SELECT
        team_id,
        min(season) AS first_season,
        max(season) AS last_season,
        string_agg(DISTINCT lg, ',' ORDER BY lg) AS leagues,
        arg_max(abbreviation, season) AS abbreviation,
        arg_max(city, season) FILTER (WHERE city IS NOT NULL) AS city,
        arg_max(espn_team_id, season) FILTER (WHERE espn_team_id IS NOT NULL) AS espn_team_id
    FROM nba.team_seasons
    GROUP BY team_id
),
latest AS (
    SELECT max(season) AS season FROM nba.team_seasons
),
names AS (
    SELECT team_id, any_value(franchise) AS name FROM nba.franchises GROUP BY team_id
)
SELECT
    s.team_id,
    n.name,
    s.abbreviation,
    s.city,
    s.first_season,
    s.last_season,
    s.last_season >= l.season - 1 AS active,
    s.espn_team_id,
    s.leagues
FROM spans s
JOIN names n USING (team_id)
CROSS JOIN latest l
