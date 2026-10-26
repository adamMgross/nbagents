WITH roster_five AS (
    SELECT game_id, team_id
    FROM sdv.espn_nba_game_rosters
    GROUP BY ALL
    HAVING count(*) FILTER (WHERE starter) = 5
),
roster_starters AS (
    SELECT g.game_id, x.player_id, bool_or(r.starter) AS starter
    FROM sdv.espn_nba_game_rosters r
    SEMI JOIN roster_five USING (game_id, team_id)
    JOIN nba.games g ON g.espn_game_id = TRY_CAST(r.game_id AS INTEGER)
    JOIN nba.player_xref x ON x.source = 'espn' AND x.source_id = r.athlete_id::VARCHAR
    GROUP BY 1, 2
),
nba AS (
    SELECT
        b.game_id, g.season, b.team_id, b.person_id::BIGINT AS player_id,
        TRY_CAST(split_part(b.minutes, ':', 1) AS INTEGER) * 60
            + coalesce(TRY_CAST(split_part(b.minutes, ':', 2) AS INTEGER), 0) AS seconds,
        b.field_goals_made AS fgm, b.field_goals_attempted AS fga,
        b.three_pointers_made AS fg3m, b.three_pointers_attempted AS fg3a,
        b.free_throws_made AS ftm, b.free_throws_attempted AS fta,
        b.rebounds_offensive AS oreb, b.rebounds_defensive AS dreb, b.rebounds_total AS reb,
        b.assists AS ast, b.steals AS stl, b.blocks AS blk, b.turnovers AS tov,
        b.fouls_personal AS pf, b.points AS pts, b.plus_minus_points AS plus_minus,
        CASE WHEN g.season >= 2018 THEN coalesce(b.position, '') <> '' ELSE rs.starter END AS started,
        CASE WHEN g.season >= 2018 THEN 'nba' WHEN rs.starter IS NOT NULL THEN 'espn' END
            AS started_source,
        nullif(b.comment, '') AS dnp_reason,
        nullif(b.jersey_num, '') AS jersey,
        nullif(b.position, '') AS position,
        'nba' AS source,
        coalesce(split_part(b.minutes, ':', 1), '') NOT IN ('', '0', '00')
            OR coalesce(TRY_CAST(split_part(b.minutes, ':', 2) AS INTEGER), 0) > 0 AS played
    FROM sdv.nba_stats_player_boxscores b
    JOIN nba.games g ON g.game_id = b.game_id
    LEFT JOIN roster_starters rs ON rs.game_id = b.game_id AND rs.player_id = b.person_id
    WHERE b.team_id <> 0 AND trim(concat(b.first_name, b.family_name)) <> ''
),
espn AS (
    SELECT
        g.game_id, g.season, t.team_id, x.player_id,
        round(b.minutes * 60)::INTEGER,
        b.field_goals_made, b.field_goals_attempted,
        b.three_point_field_goals_made, b.three_point_field_goals_attempted,
        b.free_throws_made, b.free_throws_attempted,
        b.offensive_rebounds, b.defensive_rebounds, b.rebounds,
        b.assists, b.steals, b.blocks, b.turnovers,
        b.fouls, b.points, TRY_CAST(b.plus_minus AS DOUBLE),
        coalesce(b.starter, false),
        'espn',
        CASE WHEN b.did_not_play THEN 'DNP' END,
        NULL::VARCHAR,
        nullif(b.athlete_position_abbreviation, ''),
        'espn',
        coalesce(b.minutes, 0) > 0
    FROM sdv.espn_nba_player_boxscores b
    JOIN nba.games g ON g.espn_game_id = b.game_id
    JOIN nba.team_seasons t ON t.season = g.season AND t.espn_team_id = b.team_id
    LEFT JOIN nba.player_xref x ON x.source = 'espn' AND x.source_id = b.athlete_id::VARCHAR
    WHERE g.source IN ('fte', 'espn')
)
SELECT * FROM nba
UNION ALL
SELECT * FROM espn
