WITH snapshots AS (
    SELECT * FROM sdv.espn_nba_depthcharts
    QUALIFY _fetched_at = max(_fetched_at) OVER (PARTITION BY as_of_date)
)
SELECT
    d.as_of_date AS snapshot_date,
    d.season::INTEGER AS season,
    t.team_id,
    d.team_id AS espn_team_id,
    d.position_abbreviation AS position,
    d.depth_rank,
    x.player_id,
    d.athlete_id AS espn_athlete_id,
    d.athlete_display_name AS player_name,
    d.* EXCLUDE (as_of_date, season, team_id, position_abbreviation, depth_rank, athlete_id,
                 athlete_display_name, _unit, _sha256, _fetched_at),
    d._fetched_at AS fetched_at
FROM snapshots d
LEFT JOIN nba.player_xref x ON x.source = 'espn' AND x.source_id = d.athlete_id::VARCHAR
LEFT JOIN nba.team_seasons t ON t.espn_team_id = d.team_id AND t.season = d.season
