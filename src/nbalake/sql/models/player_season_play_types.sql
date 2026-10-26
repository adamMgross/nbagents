SELECT
    season,
    CASE season_type WHEN 'regular-season' THEN 'regular' ELSE season_type END AS season_type,
    CASE side WHEN 'offensive' THEN 'offense' WHEN 'defensive' THEN 'defense' END AS side,
    play_type, player_id, player_name, team_id, team_abbreviation AS team,
    * EXCLUDE (season, season_type, per_mode, side, type_grouping, play_type, player_id,
               player_name, team_id, team_abbreviation, team_name, season_id,
               _unit, _sha256, _fetched_at)
FROM sdv.nba_stats_synergy
WHERE per_mode = 'totals'
