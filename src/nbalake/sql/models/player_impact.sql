SELECT
    season,
    CASE season_type WHEN 'Regular Season' THEN 'regular' WHEN 'Playoffs' THEN 'playoffs'
        ELSE lower(season_type) END AS season_type,
    player_id, player_name,
    team_id AS primary_team_id, team_abbreviation AS primary_team,
    string_split(teams, ',') AS teams,
    * EXCLUDE (season, season_type, player_id, player_name, team_id, team_abbreviation,
               team_name, teams, _unit, _sha256, _fetched_at)
FROM sdv.nba_player_impact
