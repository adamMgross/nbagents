-- Postseason achievement per player per playoff run from 1984: postseason_game_credit summed over the team's games that postseason, with the furthest round reached.
-- example: from postseason_season_credit() order by credit desc limit 10
CREATE OR REPLACE TEMP MACRO postseason_season_credit(baseline := 'weakest', rounds := 'linear', playoff_adjustment := true) AS TABLE
SELECT c.season, c.team_id, c.player_id, p.name AS player, count(*) AS games,
       max(c.round) AS last_round, sum(c.credit) AS credit
FROM postseason_game_credit(baseline := baseline, rounds := rounds, playoff_adjustment := playoff_adjustment) c
LEFT JOIN nba.players p ON p.player_id = c.player_id
GROUP BY ALL
