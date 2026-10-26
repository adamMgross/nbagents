WITH nba_rows AS (
    SELECT person_id::BIGINT AS nba_id, first_name || ' ' || family_name AS name,
           season::INTEGER AS season, team_id::BIGINT AS team_id
    FROM sdv.nba_stats_player_boxscores
    WHERE trim(concat(first_name, family_name)) <> ''
    UNION ALL
    SELECT player_id::BIGINT, player_name, season::INTEGER, team_id::BIGINT
    FROM sdv.leaguedash_player_bio
    UNION ALL
    SELECT TRY_CAST(nba_player_id AS BIGINT), nba_player_name, season::INTEGER, NULL
    FROM sdv.nba_player_crosswalk
    WHERE TRY_CAST(nba_player_id AS BIGINT) IS NOT NULL
),
people AS (
    SELECT 'nba' AS source, nba_id::VARCHAR AS source_id, arg_max(name, season) AS name,
           min(season) AS first_season, max(season) AS last_season
    FROM nba_rows
    GROUP BY nba_id
    UNION ALL
    SELECT 'bref', player_id, player, "from"::INTEGER, "to"::INTEGER
    FROM bref.player_career_info
),
keyed AS (
    SELECT *, string_split(key, ' ') AS tokens
    FROM (
        SELECT *, trim(regexp_replace(regexp_replace(regexp_replace(
            lower(strip_accents(name)), '[^a-z ]', '', 'g'),
            '\s+(jr|sr|ii|iii|iv|v)$', ''), '\s+', ' ', 'g')) AS key
        FROM people
    )
),
bref_people AS (SELECT * FROM keyed WHERE source = 'bref'),
nba_people AS (SELECT * FROM keyed WHERE source = 'nba'),
spans AS (
    SELECT b.source_id AS slug, n.source_id AS nba_id, b.tokens AS b_tokens, n.tokens AS n_tokens,
           b.key = n.key AS same_key, list_sort(b.tokens) = list_sort(n.tokens) AS same_tokens
    FROM bref_people b
    JOIN nba_people n
      ON b.first_season <= n.last_season + 1 AND n.first_season <= b.last_season + 1
     AND (b.tokens[1] = n.tokens[1] OR b.tokens[-1] = n.tokens[-1] OR b.tokens[1] = n.tokens[-1])
),
by_key AS (
    SELECT slug, nba_id FROM spans WHERE same_key
    QUALIFY count(*) OVER (PARTITION BY slug) = 1 AND count(*) OVER (PARTITION BY nba_id) = 1
),
by_tokens AS (
    SELECT slug, nba_id FROM spans s
    WHERE same_tokens
      AND slug NOT IN (SELECT slug FROM by_key) AND nba_id NOT IN (SELECT nba_id FROM by_key)
    QUALIFY count(*) OVER (PARTITION BY slug) = 1 AND count(*) OVER (PARTITION BY nba_id) = 1
),
bref_team_seasons AS (
    SELECT DISTINCT t.player_id AS slug, t.season::INTEGER AS season, f.team_id
    FROM bref.player_totals t
    JOIN nba.franchises f ON f.code = t.team
),
nba_team_seasons AS (
    SELECT DISTINCT nba_id::VARCHAR AS nba_id, season, team_id FROM nba_rows WHERE team_id IS NOT NULL
),
by_team_season AS (
    SELECT slug, nba_id
    FROM (
        SELECT DISTINCT s.slug, s.nba_id, s.same_key
        FROM spans s
        JOIN bref_team_seasons b ON b.slug = s.slug
        JOIN nba_team_seasons n ON n.nba_id = s.nba_id AND n.season = b.season AND n.team_id = b.team_id
        WHERE s.slug NOT IN (SELECT slug FROM by_key UNION ALL SELECT slug FROM by_tokens)
          AND s.nba_id NOT IN (SELECT nba_id FROM by_key UNION ALL SELECT nba_id FROM by_tokens)
        QUALIFY s.same_key = max(s.same_key) OVER (PARTITION BY s.slug)
            AND s.same_key = max(s.same_key) OVER (PARTITION BY s.nba_id)
    )
    QUALIFY count(*) OVER (PARTITION BY slug) = 1 AND count(*) OVER (PARTITION BY nba_id) = 1
),
bref_matched AS (
    SELECT slug, nba_id, 'name' AS method FROM by_key
    UNION ALL SELECT slug, nba_id, 'name_tokens' FROM by_tokens
    UNION ALL SELECT slug, nba_id, 'team_season_name' FROM by_team_season
),
bref_xref AS (
    SELECT
        b.source_id AS slug,
        coalesce(m.nba_id::BIGINT, 9000000000000 + md5_number_lower(b.source_id) % 1000000000000) AS player_id,
        coalesce(m.method, 'minted') AS method,
        b.name, b.first_season, b.last_season
    FROM bref_people b
    LEFT JOIN bref_matched m ON m.slug = b.source_id
),
espn_people AS (
    SELECT athlete_id::VARCHAR AS espn_id, arg_max(full_name, season) AS name,
           min(season) AS first_season, max(season) AS last_season,
           any_value(TRY_CAST(left(date_of_birth, 10) AS DATE)) AS birth_date
    FROM (
        SELECT athlete_id, full_name, season, date_of_birth FROM sdv.espn_nba_player_core
        UNION ALL
        SELECT athlete_id, athlete_display_name, season, NULL FROM sdv.espn_nba_player_boxscores
        UNION ALL
        SELECT TRY_CAST(espn_athlete_id AS BIGINT), espn_full_name, season, NULL FROM sdv.nba_player_crosswalk
        UNION ALL
        SELECT athlete_id, athlete_display_name, season, NULL FROM sdv.espn_nba_injuries
        UNION ALL
        SELECT athlete_id, athlete_display_name, season, NULL FROM sdv.espn_nba_depthcharts
    )
    WHERE athlete_id IS NOT NULL
    GROUP BY athlete_id
),
espn_crosswalk AS (
    SELECT espn_athlete_id AS espn_id, any_value(TRY_CAST(nba_player_id AS BIGINT)) AS player_id
    FROM sdv.nba_player_crosswalk
    WHERE TRY_CAST(nba_player_id AS BIGINT) IS NOT NULL
    GROUP BY espn_athlete_id
),
espn_keyed AS (
    SELECT e.*, trim(regexp_replace(regexp_replace(regexp_replace(
        lower(strip_accents(e.name)), '[^a-z ]', '', 'g'),
        '\s+(jr|sr|ii|iii|iv|v)$', ''), '\s+', ' ', 'g')) AS key
    FROM espn_people e
    ANTI JOIN espn_crosswalk c USING (espn_id)
    WHERE e.espn_id NOT IN (SELECT espn_id::VARCHAR FROM nba.espn_bref_links)
),
espn_seeded AS (
    SELECT l.espn_id::VARCHAR AS espn_id, x.player_id
    FROM nba.espn_bref_links l
    JOIN bref_xref x ON x.slug = l.bref_id
    WHERE l.espn_id::VARCHAR NOT IN (SELECT espn_id FROM espn_crosswalk)
),
espn_by_birth AS (
    SELECT e.espn_id, x.player_id
    FROM espn_keyed e
    JOIN bref_people b ON b.key = e.key
    JOIN bref.player_career_info i ON i.player_id = b.source_id AND i.birth_date = e.birth_date
    JOIN bref_xref x ON x.slug = b.source_id
    QUALIFY count(*) OVER (PARTITION BY e.espn_id) = 1
),
espn_by_span AS (
    SELECT e.espn_id, x.player_id
    FROM espn_keyed e
    JOIN bref_people b
      ON b.key = e.key AND b.first_season <= e.last_season + 1 AND e.first_season <= b.last_season + 1
    JOIN bref_xref x ON x.slug = b.source_id
    WHERE e.espn_id NOT IN (SELECT espn_id FROM espn_by_birth)
    QUALIFY count(*) OVER (PARTITION BY e.espn_id) = 1
),
espn_by_bref AS (
    SELECT espn_id, player_id, 'crosswalk' AS method FROM espn_crosswalk
    UNION ALL SELECT espn_id, player_id, 'seed' FROM espn_seeded
    UNION ALL SELECT espn_id, player_id, 'name_birth_date' FROM espn_by_birth
    UNION ALL SELECT espn_id, player_id, 'name_span' FROM espn_by_span
),
espn_by_nba_span AS (
    SELECT e.espn_id, n.source_id::BIGINT AS player_id
    FROM espn_keyed e
    JOIN nba_people n
      ON n.key = e.key AND n.first_season <= e.last_season + 1 AND e.first_season <= n.last_season + 1
    WHERE e.espn_id NOT IN (SELECT espn_id FROM espn_by_bref)
      AND n.source_id::BIGINT NOT IN (SELECT player_id FROM espn_by_bref)
    QUALIFY count(*) OVER (PARTITION BY e.espn_id) = 1
        AND count(*) OVER (PARTITION BY n.source_id) = 1
),
espn_xref AS (
    SELECT * FROM espn_by_bref
    UNION ALL SELECT espn_id, player_id, 'nba_name_span' FROM espn_by_nba_span
),
fte_ids AS (
    SELECT player_id AS slug, any_value(player_name) AS name,
           min(season)::INTEGER AS first_season, max(season)::INTEGER AS last_season
    FROM (
        SELECT player_id, player_name, season FROM fte.raptor_player_historical
        UNION ALL
        SELECT player_id, player_name, season FROM fte.raptor_player_modern
    )
    GROUP BY player_id
)
SELECT 'nba' AS source, source_id, source_id::BIGINT AS player_id, 'identity' AS method,
       name, first_season, last_season
FROM nba_people
UNION ALL
SELECT 'bref', slug, player_id, method, name, first_season, last_season FROM bref_xref
UNION ALL
SELECT 'espn', x.espn_id, x.player_id, x.method, p.name, p.first_season, p.last_season
FROM espn_xref x JOIN espn_people p USING (espn_id)
UNION ALL
SELECT 'fte', f.slug, x.player_id, 'bref_slug', f.name, f.first_season, f.last_season
FROM fte_ids f JOIN bref_xref x USING (slug)
