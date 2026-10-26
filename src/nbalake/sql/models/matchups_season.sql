SELECT
    season,
    CASE season_type WHEN 'regular-season' THEN 'regular' ELSE season_type END AS season_type,
    off_player_id, def_player_id, gp,
    matchup_time_sec AS matchup_seconds,
    * EXCLUDE (
        season_id, season, season_type, per_mode, off_player_id, off_player_name,
        def_player_id, def_player_name, gp, matchup_time_sec, matchup_min,
        _unit, _sha256, _fetched_at
    )
FROM sdv.season_matchups
WHERE per_mode = 'totals'
