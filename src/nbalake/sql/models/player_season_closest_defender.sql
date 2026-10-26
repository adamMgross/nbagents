SELECT
    g.season,
    g.season_type,
    g.PLAYER_ID AS player_id,
    g.PLAYER AS player_name,
    ts.team_id AS last_team_id,
    coalesce(ts.abbreviation, g.TEAM) AS last_team,
    g.AGE AS age,
    g.GP AS gp,
    g.defender_distance,
    CASE g.defender_distance
        WHEN 'very_tight' THEN 0 WHEN 'tight' THEN 2 WHEN 'open' THEN 4 WHEN 'wide_open' THEN 6
    END AS defender_ft_min,
    g.G AS games_with_shot,
    g.FGM AS fgm,
    g.FGA AS fga,
    g."2FGM" AS fg2m,
    g."2FGA" AS fg2a,
    g."3PM" AS fg3m,
    g."3PA" AS fg3a
FROM gab.player_shots_by_defender g
LEFT JOIN nba.team_seasons ts
    ON ts.season = g.season AND (ts.abbreviation = g.TEAM OR ts.name = g.TEAM)
