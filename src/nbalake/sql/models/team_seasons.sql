WITH bref AS (
    SELECT
        s.season::INTEGER AS season, s.lg, f.team_id, s.abbreviation AS bref_abbr, s.team AS bref_name,
        s.playoffs::BOOLEAN AS playoffs, s.w::INTEGER AS w, s.l::INTEGER AS l,
        s.mov, s.srs, s.pace, s.o_rtg, s.d_rtg, s.n_rtg, s.arena, s.attend::INTEGER AS attend
    FROM bref.team_summaries s
    JOIN nba.franchises f ON f.code = s.abbreviation
),
crosswalk AS (
    SELECT
        season::INTEGER AS season, TRY_CAST(nba_team_id AS BIGINT) AS team_id,
        any_value(nba_team_city) AS city, any_value(nba_team_name) AS nickname,
        any_value(espn_team_id::INTEGER) AS espn_team_id
    FROM sdv.nba_team_crosswalk
    WHERE TRY_CAST(nba_team_id AS BIGINT) IS NOT NULL
    GROUP BY ALL
),
espn_ids AS (
    SELECT espn_team_id::INTEGER AS espn_team_id, arg_min(TRY_CAST(nba_team_id AS BIGINT), season) AS team_id
    FROM sdv.nba_team_crosswalk
    WHERE TRY_CAST(nba_team_id AS BIGINT) IS NOT NULL
    GROUP BY ALL
),
groups AS (
    SELECT
        g.season::INTEGER AS season,
        coalesce(TRY_CAST(regexp_extract(g.notes, 'nba_stats_team_id=(\d+)', 1) AS BIGINT), e.team_id) AS team_id,
        any_value(g.team_id::INTEGER) AS espn_team_id,
        any_value(g.team_name) AS espn_name,
        any_value(replace(g.conference_id, 'nba:', '')) AS conference,
        any_value(replace(g.division_id, 'nba:', '')) AS division
    FROM sdv.nba_team_group_seasons g
    LEFT JOIN espn_ids e ON e.espn_team_id = g.team_id::INTEGER
    WHERE g.league = 'nba'
    GROUP BY ALL
),
tricodes AS (
    SELECT season::INTEGER AS season, team_id, max(abbr) AS abbreviation
    FROM (
        SELECT season, home_team_id AS team_id, home_team_abbreviation AS abbr FROM sdv.nba_stats_schedules
        UNION ALL
        SELECT season, away_team_id, away_team_abbreviation FROM sdv.nba_stats_schedules
    )
    WHERE team_id BETWEEN 1610612737 AND 1610612766
    GROUP BY ALL
),
keys AS (
    SELECT season, team_id FROM bref
    UNION SELECT season, team_id FROM crosswalk
    UNION SELECT season, team_id FROM groups
    UNION SELECT season, team_id FROM tricodes
)
SELECT
    k.season,
    k.team_id,
    coalesce(b.lg, 'NBA') AS lg,
    coalesce(
        t.abbreviation,
        b.bref_abbr,
        last_value(t.abbreviation IGNORE NULLS) OVER (PARTITION BY k.team_id ORDER BY k.season)
    ) AS abbreviation,
    coalesce(c.nickname, b.bref_name, g.espn_name) AS name,
    c.city,
    g.conference,
    g.division,
    coalesce(c.espn_team_id, g.espn_team_id) AS espn_team_id,
    b.bref_abbr,
    b.playoffs, b.w, b.l, b.mov, b.srs, b.pace, b.o_rtg, b.d_rtg, b.n_rtg, b.arena, b.attend
FROM keys k
LEFT JOIN bref b USING (season, team_id)
LEFT JOIN crosswalk c USING (season, team_id)
LEFT JOIN groups g USING (season, team_id)
LEFT JOIN tricodes t USING (season, team_id)
