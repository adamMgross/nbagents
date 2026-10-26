SELECT series_id, best_of, home_court_wins, other_wins, games, winner_team_id
FROM nba.playoff_series
WHERE home_court_wins + other_wins <> games
   OR games > best_of
   OR (winner_team_id IS NOT NULL AND (
        greatest(home_court_wins, other_wins) <> (best_of + 1) // 2
        OR least(home_court_wins, other_wins) >= (best_of + 1) // 2
        OR winner_team_id <> CASE WHEN home_court_wins > other_wins THEN home_court_team_id ELSE other_team_id END))
   OR (winner_team_id IS NULL AND greatest(home_court_wins, other_wins) >= (best_of + 1) // 2)
