SELECT
    season,
    CASE season_type WHEN 'regular-season' THEN 'regular' ELSE season_type END AS season_type,
    team_id, team_name,
    * EXCLUDE (season, season_type, per_mode, team_id, team_name, _unit, _sha256, _fetched_at)
FROM sdv.hustle_team
WHERE per_mode = 'totals'
