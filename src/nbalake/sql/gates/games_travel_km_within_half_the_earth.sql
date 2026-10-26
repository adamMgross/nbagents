SELECT game_id, team_id, travel_km
FROM nba.team_games
WHERE travel_km < 0 OR travel_km > 20016
