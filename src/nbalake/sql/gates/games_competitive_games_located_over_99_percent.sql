SELECT located, games
FROM (
    SELECT count(travel_km) AS located, count(rest_days) AS games
    FROM nba.team_games
)
WHERE located < 0.99 * games
