WITH unioned AS (
    SELECT 'modern' AS model, * EXCLUDE (_unit, _sha256, _fetched_at) FROM fte.raptor_player_modern
    UNION ALL BY NAME
    SELECT 'historical' AS model, * EXCLUDE (_unit, _sha256, _fetched_at) FROM fte.raptor_player_historical
)
SELECT
    u.season::INTEGER AS season,
    x.player_id,
    u.player_id AS bref_id,
    u.* EXCLUDE (season, player_id)
FROM unioned u
LEFT JOIN nba.player_xref x ON x.source = 'fte' AND x.source_id = u.player_id
