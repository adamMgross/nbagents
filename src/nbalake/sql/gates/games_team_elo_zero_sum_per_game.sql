SELECT game_id, count(*) AS sides, sum(elo_post - elo_pre) AS net, sum(fit_post - fit_pre) AS fit_net
FROM nba.team_elo
GROUP BY game_id
HAVING count(*) <> 2 OR abs(sum(elo_post - elo_pre)) > 1e-6 OR abs(sum(fit_post - fit_pre)) > 1e-6
