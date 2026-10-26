-- Career wins above replacement per NBA player from 1974, era_wins_season summed, with the best season and the best five seasons in neutral wins, and partial true for a career that began before first_season.
-- example: from career_era_wins() limit 20
CREATE OR REPLACE TEMP MACRO career_era_wins(first_season := 1974, reference_season := 2026) AS TABLE
WITH seasons AS (
    SELECT s.*,
           row_number() OVER (PARTITION BY s.player_id ORDER BY s.neutral_wins DESC) AS best_order
    FROM era_wins_season(first_season := first_season, reference_season := reference_season) s
)
SELECT rank() OVER (ORDER BY sum(s.neutral_wins) DESC) AS rank, s.player_id,
       any_value(s.player) AS player, count(*) AS seasons, min(s.season) AS first_season,
       max(s.season) AS last_season, any_value(p.from_season) < min(s.season) AS partial,
       sum(s.wins) AS wins, sum(s.neutral_wins) AS neutral_wins,
       sum(s.neutral_wins) FILTER (WHERE s.best_order <= 5) AS best_five_neutral_wins,
       arg_max(s.season, s.neutral_wins) AS best_season, max(s.neutral_wins) AS best_neutral_wins
FROM seasons s
LEFT JOIN nba.players p ON p.player_id = s.player_id
GROUP BY s.player_id
ORDER BY neutral_wins DESC
