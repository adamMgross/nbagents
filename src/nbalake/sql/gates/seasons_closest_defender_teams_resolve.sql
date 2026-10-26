SELECT DISTINCT season, season_type, 'player' AS side, last_team AS team
FROM nba.player_season_closest_defender
WHERE last_team_id IS NULL
UNION ALL
SELECT DISTINCT season, season_type, side, team
FROM nba.team_season_closest_defender
WHERE team_id IS NULL
