-- Career postseason achievement per player from 1984: postseason_season_credit summed over every run, with the best run and its credit.
-- example: from career_postseason() limit 20
CREATE OR REPLACE TEMP MACRO career_postseason(baseline := 'weakest', rounds := 'linear', playoff_adjustment := true) AS TABLE
SELECT rank() OVER (ORDER BY sum(s.credit) DESC) AS rank, s.player_id, any_value(s.player) AS player,
       count(*) AS runs, min(s.season) AS first_season, max(s.season) AS last_season,
       sum(s.credit) AS credit, arg_max(s.season, s.credit) AS best_season, max(s.credit) AS best_credit
FROM postseason_season_credit(baseline := baseline, rounds := rounds, playoff_adjustment := playoff_adjustment) s
GROUP BY s.player_id
ORDER BY credit DESC
