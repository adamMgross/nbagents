-- Career quality wins per NBA and BAA player from 1947: quality_win_season summed over every team and season, with the best season and its credit.
-- example: from career_quality_wins() limit 20
CREATE OR REPLACE TEMP MACRO career_quality_wins(shares := 'win_shares') AS TABLE
WITH seasons AS (
    SELECT season, player_id, any_value(player) AS player, sum(credit) AS credit
    FROM quality_win_season(shares := shares)
    GROUP BY ALL
)
SELECT rank() OVER (ORDER BY sum(s.credit) DESC) AS rank, s.player_id, any_value(s.player) AS player,
       count(*) AS seasons, min(s.season) AS first_season, max(s.season) AS last_season,
       sum(s.credit) AS credit, arg_max(s.season, s.credit) AS best_season, max(s.credit) AS best_credit
FROM seasons s
GROUP BY s.player_id
ORDER BY credit DESC
