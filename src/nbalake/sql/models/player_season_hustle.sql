SELECT
    season,
    CASE season_type WHEN 'regular-season' THEN 'regular' ELSE season_type END AS season_type,
    player_id, player_name,
    team_id AS last_team_id, team_abbreviation AS last_team,
    age, g AS gp,
    * EXCLUDE (season, season_type, per_mode, player_id, player_name, team_id, team_abbreviation,
               age, g, _unit, _sha256, _fetched_at)
FROM sdv.hustle_player
WHERE per_mode = 'totals'
