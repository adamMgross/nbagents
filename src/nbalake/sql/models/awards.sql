WITH shares AS (
    SELECT
        season::INTEGER AS season,
        upper(split_part(award, ' ', 1)) AS lg,
        split_part(award, ' ', 2) AS award,
        player_id AS bref_id,
        NULL::VARCHAR AS detail,
        share, winner::BOOLEAN AS winner, first AS first_place_votes, pts_won, pts_max
    FROM bref.player_award_shares
),
all_stars AS (
    SELECT season::INTEGER, lg, 'all_star', player_id, team, NULL::DOUBLE, NOT coalesce(replaced, false),
           NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE
    FROM bref.all_star_selections
),
teams AS (
    SELECT season::INTEGER, lg, lower(replace(type, '-', '_')), player_id, number_tm, NULL::DOUBLE, true,
           NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE
    FROM bref.end_of_season_teams
),
unioned AS (
    SELECT * FROM shares
    UNION ALL SELECT * FROM all_stars
    UNION ALL SELECT * FROM teams
)
SELECT u.season, u.lg, u.award, x.player_id, u.* EXCLUDE (season, lg, award)
FROM unioned u
LEFT JOIN nba.player_xref x ON x.source = 'bref' AND x.source_id = u.bref_id
