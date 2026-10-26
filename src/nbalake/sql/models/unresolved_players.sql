WITH espn AS (
    SELECT athlete_id::VARCHAR AS source_id, arg_max(name, season) AS name,
           min(season) AS first_season, max(season) AS last_season
    FROM (
        SELECT athlete_id, full_name AS name, season FROM sdv.espn_nba_player_core
        UNION ALL
        SELECT athlete_id, athlete_display_name, season FROM sdv.espn_nba_player_boxscores
    )
    WHERE athlete_id IS NOT NULL
    GROUP BY athlete_id
),
fte AS (
    SELECT player_id AS source_id, any_value(player_name) AS name,
           min(season)::INTEGER AS first_season, max(season)::INTEGER AS last_season
    FROM (
        SELECT player_id, player_name, season FROM fte.raptor_player_historical
        UNION ALL
        SELECT player_id, player_name, season FROM fte.raptor_player_modern
    )
    GROUP BY player_id
)
SELECT 'espn' AS source, e.source_id, e.name, e.first_season, e.last_season,
       'no crosswalk row and no unique name match' AS reason
FROM espn e
ANTI JOIN nba.player_xref x ON x.source = 'espn' AND x.source_id = e.source_id
UNION ALL
SELECT 'fte', f.source_id, f.name, f.first_season, f.last_season, 'slug not in Basketball-Reference'
FROM fte f
ANTI JOIN nba.player_xref x ON x.source = 'fte' AND x.source_id = f.source_id
