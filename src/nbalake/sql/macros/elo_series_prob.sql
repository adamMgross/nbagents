-- The Elo chance the team with home court wins a best_of series, hosting (best_of + 1) / 2 of the games, as nba.playoff_series.home_court_series_prob.
-- example: select elo_series_prob(1790, 1725, 7)
CREATE OR REPLACE TEMP MACRO elo_series_prob(elo_home_court, elo_other, best_of := 7, home_edge := 100) AS
    list_sum([
        pow(elo_game_prob(elo_home_court, elo_other, home_edge), bit_count(m & ((1 << ((best_of + 1) // 2)) - 1)))
            * pow(1 - elo_game_prob(elo_home_court, elo_other, home_edge),
                  (best_of + 1) // 2 - bit_count(m & ((1 << ((best_of + 1) // 2)) - 1)))
            * pow(1 - elo_game_prob(elo_other, elo_home_court, home_edge), bit_count(m >> ((best_of + 1) // 2)))
            * pow(elo_game_prob(elo_other, elo_home_court, home_edge),
                  (best_of - 1) // 2 - bit_count(m >> ((best_of + 1) // 2)))
        FOR m IN range(1 << best_of) IF bit_count(m) >= (best_of + 1) // 2
    ]);
