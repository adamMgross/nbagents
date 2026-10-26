-- League strength per NBA season from 1974 in BPM points against reference_season: year to year steps from players with min_minutes in back to back seasons, age curve removed, and the long run trend from the US talent pool behind each season's US-born roster spots.
-- example: from league_strength() order by season
CREATE OR REPLACE TEMP MACRO league_strength(min_minutes := 800, reference_season := 2026) AS TABLE
WITH args AS (
    SELECT CASE WHEN min_minutes > 0 THEN min_minutes
                ELSE error('min_minutes must be positive') END AS min_minutes,
           reference_season AS reference_season
),
players AS (
    SELECT s.season, s.player_id, s.bref_id, least(greatest(s.age, 20), 37) AS age, s.mp, s.bpm,
           a.min_minutes
    FROM args a
    JOIN nba.player_seasons s ON s.lg = 'NBA' AND s.bpm IS NOT NULL
    QUALIFY count(*) OVER (PARTITION BY s.season, s.player_id) = 1 OR s.multi_team
),
pairs AS (
    SELECT c.season, c.age, c.bpm - p.bpm AS d, 2.0 / (1.0 / c.mp + 1.0 / p.mp) AS w
    FROM players c
    JOIN players p ON p.player_id = c.player_id AND p.season = c.season - 1
    WHERE c.mp >= c.min_minutes AND p.mp >= c.min_minutes
),
year_mean AS (
    SELECT season, sum(w * d) / sum(w) AS y FROM pairs GROUP BY season
),
age_curve AS (
    SELECT p.age, sum(p.w * (p.d - y.y)) / sum(p.w) AS g
    FROM pairs p JOIN year_mean y USING (season)
    GROUP BY p.age
),
shocks AS (
    SELECT p.season, sum(p.w * (p.d - g.g)) / sum(p.w) AS shock
    FROM pairs p JOIN age_curve g USING (age)
    GROUP BY p.season
),
foreign_born AS (
    SELECT s.season,
           sum(s.mp) FILTER (WHERE NOT b.born_in_us)
               / sum(s.mp) FILTER (WHERE b.born_in_us IS NOT NULL) AS foreign_share
    FROM players s JOIN nba.player_birthplaces b USING (bref_id)
    GROUP BY s.season
),
teams AS (
    SELECT t.season, count(*) FILTER (WHERE t.lg IN ('NBA', 'ABA')) AS teams
    FROM args a
    JOIN nba.team_seasons t ON t.season >= 1974
    GROUP BY t.season
),
pool AS (
    SELECT t.season, f.foreign_share, 10 * t.teams * (1 - f.foreign_share) AS us_spots, u.population
    FROM teams t
    JOIN foreign_born f USING (season)
    ASOF JOIN nba.us_population u ON t.season >= u.year
),
talent AS (
    SELECT season, foreign_share, us_spots,
           r - (2.515517 + 0.802853 * r + 0.010328 * r * r)
               / (1 + 1.432788 * r + 0.189269 * r * r + 0.001308 * r * r * r) AS talent_z
    FROM (SELECT *, sqrt(-2 * ln(us_spots / population)) AS r FROM pool)
),
steps AS (
    SELECT t.season, t.foreign_share, t.us_spots, t.talent_z,
           t.talent_z - lag(t.talent_z) OVER (ORDER BY t.season) AS talent_step, s.shock
    FROM talent t LEFT JOIN shocks s USING (season)
),
fit AS (
    SELECT regr_intercept(shock, talent_step) AS drift, regr_slope(shock, talent_step) AS slope
    FROM steps
),
levels AS (
    SELECT s.*, -f.slope AS bpm_per_talent_sd,
           sum(coalesce(f.drift - s.shock, 0)) OVER (ORDER BY s.season) AS level
    FROM steps s, fit f
)
SELECT l.season, l.foreign_share, l.us_spots, l.talent_z, l.shock, l.bpm_per_talent_sd,
       l.level - max(l.level) FILTER (WHERE l.season = a.reference_season) OVER () AS strength
FROM levels l, args a
ORDER BY l.season
