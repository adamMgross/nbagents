SELECT
    official_id,
    arg_max(name, season) AS name,
    min(season) AS from_season,
    max(season) AS to_season,
    count(*) AS games
FROM nba.game_officials
GROUP BY official_id
