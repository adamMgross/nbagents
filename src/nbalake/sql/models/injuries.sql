WITH snapshots AS (
    SELECT * FROM sdv.espn_nba_injuries
    QUALIFY _fetched_at = max(_fetched_at) OVER (PARTITION BY as_of_date)
)
SELECT
    i.as_of_date AS snapshot_date,
    i.season::INTEGER AS season,
    x.player_id,
    i.athlete_id AS espn_athlete_id,
    i.athlete_display_name AS player_name,
    t.team_id,
    i.team_id AS espn_team_id,
    i.status,
    timezone('UTC', TRY_CAST(i.injury_date AS TIMESTAMPTZ)) AS reported_at,
    TRY_CAST(i.detail_return_date AS DATE) AS return_date,
    i.* EXCLUDE (as_of_date, season, athlete_id, athlete_display_name, team_id, status,
                 injury_date, detail_return_date, _unit, _sha256, _fetched_at),
    i._fetched_at AS fetched_at
FROM snapshots i
LEFT JOIN nba.player_xref x ON x.source = 'espn' AND x.source_id = i.athlete_id::VARCHAR
LEFT JOIN nba.team_seasons t ON t.espn_team_id = i.team_id AND t.season = i.season
