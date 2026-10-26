SELECT
    * EXCLUDE (_unit, _sha256, _fetched_at, person_id),
    nullif(person_id, 0) AS player_id,
    shot_result = 'Made' AS made,
    x_legacy / 10.0 AS x_feet,
    y_legacy / 10.0 AS y_feet
FROM sdv.nba_stats_shots
