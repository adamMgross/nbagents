-- A player's shots by zone with attempts, makes, percentage, share of his attempts, and the league percentage and share for the same zone and season.
-- example: from shot_zones(201939, 2016)
CREATE OR REPLACE TEMP MACRO shot_zones(player_id, season, season_type := 'regular') AS TABLE
WITH args AS (
    SELECT player_id AS player_id, season AS season,
        CASE season_type WHEN 'regular' THEN '2' WHEN 'playoffs' THEN '4'
            WHEN 'play-in' THEN '5' WHEN 'nba-cup' THEN '6' END AS season_type_id
),
s AS (
    SELECT sh.player_id = a.player_id AS mine, sh.made,
        CASE
            WHEN sh.shot_value = 3 AND abs(sh.x_feet) >= 22 AND sh.y_feet <= 8.75 THEN 'corner 3'
            WHEN sh.shot_value = 3 THEN 'above the break 3'
            WHEN sh.shot_distance < 4 THEN 'restricted area'
            WHEN abs(sh.x_feet) <= 8 AND sh.y_feet <= 13.75 THEN 'paint'
            ELSE 'midrange'
        END AS zone
    FROM args a
    JOIN nba.shots sh ON sh.season = a.season
    WHERE a.season_type_id IS NULL OR sh.season_type_id = a.season_type_id
),
league AS (
    SELECT s.zone, avg(s.made::INTEGER) AS fg_pct, count(*) / sum(count(*)) OVER () AS share
    FROM s GROUP BY s.zone
),
player AS (
    SELECT s.zone, count(*) AS attempts, count(*) FILTER (WHERE s.made) AS made,
        avg(s.made::INTEGER) AS fg_pct, count(*) / sum(count(*)) OVER () AS share
    FROM s WHERE s.mine GROUP BY s.zone
)
SELECT p.zone, p.attempts, p.made, p.fg_pct, p.share,
    l.fg_pct AS league_fg_pct, l.share AS league_share, p.fg_pct - l.fg_pct AS fg_pct_vs_league
FROM player p JOIN league l ON l.zone = p.zone
ORDER BY p.attempts DESC;
