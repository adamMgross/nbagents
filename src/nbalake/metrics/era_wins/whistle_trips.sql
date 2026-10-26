-- Free throw trips the whistle gives each NBA player per regular season from 1997 play-by-play, by channel: two-shot trips after a shooting foul, and-ones, and three-shot trips.
-- example: from whistle_trips() where season = 2019 order by three_trips desc limit 10
CREATE OR REPLACE TEMP MACRO whistle_trips(first_season := 1997) AS TABLE
WITH args AS (
    SELECT first_season AS first_season
),
events AS (
    SELECT p.game_id, p.order_index, p.season, p.player_id, p.sub_type, p.is_foul
    FROM args a
    JOIN nba.pbp p ON p.season >= greatest(a.first_season, 1997)
    WHERE p.game_id LIKE '002%' AND (p.is_foul OR p.is_free_throw)
),
fouls AS (
    SELECT game_id, order_index, sub_type FROM events WHERE is_foul
),
trips AS (
    SELECT t.season, t.player_id, t.sub_type, f.sub_type AS foul
    FROM events t
    ASOF JOIN fouls f ON t.game_id = f.game_id AND t.order_index > f.order_index
    WHERE NOT t.is_foul
      AND t.sub_type IN ('Free Throw 1 of 2', 'Free Throw 1 of 1', 'Free Throw 1 of 3')
)
SELECT season, player_id,
       count(*) FILTER (WHERE sub_type = 'Free Throw 1 of 2' AND foul = 'Shooting') AS two_trips,
       count(*) FILTER (WHERE sub_type = 'Free Throw 1 of 1') AS and_ones,
       count(*) FILTER (WHERE sub_type = 'Free Throw 1 of 3') AS three_trips
FROM trips
GROUP BY ALL
