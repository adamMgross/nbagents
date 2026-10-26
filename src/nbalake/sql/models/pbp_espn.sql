SELECT
    p.* EXCLUDE (_unit, _sha256, _fetched_at, game_id, coordinate_x, coordinate_y, coordinate_x_raw, coordinate_y_raw),
    p.game_id AS espn_game_id,
    g.game_id,
    CASE WHEN abs(p.coordinate_x) <= 100 THEN p.coordinate_x END AS coordinate_x,
    CASE WHEN abs(p.coordinate_y) <= 100 THEN p.coordinate_y END AS coordinate_y,
    CASE WHEN abs(p.coordinate_x_raw) <= 100 THEN p.coordinate_x_raw END AS coordinate_x_raw,
    CASE WHEN abs(p.coordinate_y_raw) <= 100 THEN p.coordinate_y_raw END AS coordinate_y_raw
FROM sdv.espn_nba_pbp p
LEFT JOIN nba.games g ON g.espn_game_id = p.game_id
