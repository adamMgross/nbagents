-- The Elo chance the home team wins one game. nba.team_games.elo_win_prob uses home_edge 100, and 0 at a neutral site.
-- example: select elo_game_prob(1790, 1725)
CREATE OR REPLACE TEMP MACRO elo_game_prob(elo_home, elo_away, home_edge := 100) AS
    1 / (1 + pow(10, -(elo_home - elo_away + home_edge) / 400));
