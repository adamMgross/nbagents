WITH ids AS (
    SELECT
        player_id,
        max(CASE WHEN source = 'nba' THEN source_id::BIGINT END) AS nba_player_id,
        any_value(source_id) FILTER (WHERE source = 'bref') AS bref_id,
        arg_max(CASE WHEN source = 'espn' THEN source_id::BIGINT END, last_season) FILTER (WHERE source = 'espn') AS espn_athlete_id,
        coalesce(any_value(name) FILTER (WHERE source = 'nba'), any_value(name) FILTER (WHERE source = 'bref'),
                 any_value(name)) AS name,
        min(first_season) AS from_season,
        max(last_season) AS to_season
    FROM nba.player_xref
    GROUP BY player_id
),
nba_names AS (
    SELECT person_id::BIGINT AS nba_player_id,
           arg_max(first_name, season) AS first_name, arg_max(family_name, season) AS last_name
    FROM sdv.nba_stats_player_boxscores
    GROUP BY 1
),
bio AS (
    SELECT
        player_id::BIGINT AS nba_player_id,
        arg_max(TRY_CAST(player_height_inches AS INTEGER), season) AS height_inches,
        arg_max(TRY_CAST(player_weight AS INTEGER), season) AS weight_lbs,
        arg_max(nullif(nullif(college, 'None'), ''), season) AS college,
        arg_max(nullif(country, ''), season) AS country,
        arg_max(TRY_CAST(draft_year AS INTEGER), season) AS draft_year,
        arg_max(TRY_CAST(draft_round AS INTEGER), season) AS draft_round,
        arg_max(TRY_CAST(draft_number AS INTEGER), season) AS draft_pick
    FROM sdv.leaguedash_player_bio
    GROUP BY 1
),
espn AS (
    SELECT
        athlete_id AS espn_athlete_id,
        arg_max(TRY_CAST(left(date_of_birth, 10) AS DATE), season) AS birth_date,
        arg_max(height::INTEGER, season) AS height_inches,
        arg_max(weight::INTEGER, season) AS weight_lbs,
        arg_max(nullif(birth_country, ''), season) AS country
    FROM sdv.espn_nba_player_core
    GROUP BY 1
)
SELECT
    i.player_id,
    i.name,
    coalesce(n.first_name, split_part(i.name, ' ', 1)) AS first_name,
    coalesce(n.last_name, nullif(trim(substr(i.name, length(split_part(i.name, ' ', 1)) + 1)), '')) AS last_name,
    coalesce(c.birth_date, e.birth_date) AS birth_date,
    coalesce(b.height_inches, c.ht_in_in::INTEGER, e.height_inches) AS height_inches,
    coalesce(b.weight_lbs, c.wt::INTEGER, e.weight_lbs) AS weight_lbs,
    coalesce(b.college, nullif(c.colleges, '')) AS college,
    coalesce(b.country, e.country) AS country,
    b.draft_year,
    b.draft_round,
    b.draft_pick,
    i.from_season,
    i.to_season,
    coalesce(c.hof, false) AS hof,
    i.nba_player_id,
    i.espn_athlete_id,
    i.bref_id
FROM ids i
LEFT JOIN nba_names n USING (nba_player_id)
LEFT JOIN bio b USING (nba_player_id)
LEFT JOIN bref.player_career_info c ON c.player_id = i.bref_id
LEFT JOIN espn e USING (espn_athlete_id)
