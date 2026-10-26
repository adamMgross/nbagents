-- Basic career postseason achievement per player from first_season: postseason_basic_season_credit summed over every run, with the best run and its credit.
-- example: from career_postseason_basic() limit 20
CREATE OR REPLACE TEMP MACRO career_postseason_basic(baseline := 'weakest', rounds := 'from_final', first_season := 1958) AS TABLE
SELECT rank() OVER (ORDER BY sum(s.credit) DESC) AS rank, s.player_id, any_value(s.player) AS player,
       count(*) AS runs, min(s.season) AS first_season, max(s.season) AS last_season,
       sum(s.credit) AS credit, arg_max(s.season, s.credit) AS best_season, max(s.credit) AS best_credit
FROM postseason_basic_season_credit(baseline := baseline, rounds := rounds, first_season := first_season) s
GROUP BY s.player_id
ORDER BY credit DESC
