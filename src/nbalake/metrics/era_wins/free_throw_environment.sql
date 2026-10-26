-- The free throw whistle per NBA regular season from 1974 by channel: two-shot shooting trips per two-point attempt within 10 feet, and-ones per make within 10 feet, three-shot trips per three-point attempt, and each channel's share of free throws, 1997 values carried back before play-by-play.
-- example: from free_throw_environment() where season >= 2015
CREATE OR REPLACE TEMP MACRO free_throw_environment(first_season := 1974) AS TABLE
WITH args AS (
    SELECT CASE WHEN first_season >= 1974 THEN first_season
                ELSE error('first_season must be 1974 or later') END AS first_season
),
league AS (
    SELECT t.season, sum(t.fta) AS fta, sum(coalesce(t.x3pa, 0)) AS x3pa
    FROM args a
    JOIN nba.team_season_stats t ON t.lg = 'NBA' AND t.season >= a.first_season
    GROUP BY t.season
),
near AS (
    SELECT s.season, count(*) AS near_twos, count(*) FILTER (WHERE s.made) AS near_makes
    FROM args a
    JOIN nba.shots s ON s.season >= greatest(a.first_season, 1997)
    WHERE s.game_id LIKE '002%' AND s.shot_value = 2 AND s.shot_distance <= 10
    GROUP BY s.season
),
trips AS (
    SELECT season, sum(two_trips) AS two_trips, sum(and_ones) AS and_ones,
           sum(three_trips) AS three_trips
    FROM whistle_trips()
    GROUP BY season
),
rates AS (
    SELECT l.season, l.x3pa, r.season IS NOT NULL AS measured,
           r.two_trips / n.near_twos AS two_rate, r.and_ones / n.near_makes AS and_one_rate,
           r.three_trips / nullif(l.x3pa, 0) AS three_rate,
           2 * r.two_trips / l.fta AS two_share, r.and_ones / l.fta AS and_one_share,
           3 * r.three_trips / l.fta AS three_share
    FROM league l LEFT JOIN trips r USING (season) LEFT JOIN near n USING (season)
),
first_measured AS (
    SELECT * FROM rates WHERE measured ORDER BY season LIMIT 1
)
SELECT r.season, r.measured,
       coalesce(r.two_rate, f.two_rate) AS two_rate,
       coalesce(r.and_one_rate, f.and_one_rate) AS and_one_rate,
       coalesce(r.three_rate, f.three_rate) AS three_rate,
       coalesce(r.two_share, f.two_share) AS two_share,
       coalesce(r.and_one_share, f.and_one_share) AS and_one_share,
       CASE WHEN r.x3pa = 0 THEN 0 ELSE coalesce(r.three_share, f.three_share) END AS three_share
FROM rates r, first_measured f
ORDER BY r.season
