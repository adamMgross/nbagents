WITH nba AS (
    SELECT
        b.game_id, g.season, b.team_id,
        CASE WHEN b.team_id = g.home_team_id THEN g.away_team_id ELSE g.home_team_id END AS opponent_team_id,
        b.team_id = g.home_team_id AS is_home,
        TRY_CAST(split_part(b.minutes, ':', 1) AS INTEGER) * 60
            + coalesce(TRY_CAST(split_part(b.minutes, ':', 2) AS INTEGER), 0) AS seconds,
        b.field_goals_made AS fgm, b.field_goals_attempted AS fga,
        b.three_pointers_made AS fg3m, b.three_pointers_attempted AS fg3a,
        b.free_throws_made AS ftm, b.free_throws_attempted AS fta,
        b.rebounds_offensive AS oreb, b.rebounds_defensive AS dreb, b.rebounds_total AS reb,
        b.assists AS ast, b.steals AS stl, b.blocks AS blk, b.turnovers AS tov,
        b.fouls_personal AS pf, b.points AS pts, b.plus_minus_points AS plus_minus,
        'nba' AS source
    FROM sdv.nba_stats_team_boxscores b
    JOIN nba.games g ON g.game_id = b.game_id
    WHERE b.team_id <> 0
),
espn AS (
    SELECT
        g.game_id, g.season, t.team_id,
        CASE WHEN t.team_id = g.home_team_id THEN g.away_team_id ELSE g.home_team_id END,
        t.team_id = g.home_team_id,
        NULL::INTEGER,
        b.field_goals_made, b.field_goals_attempted,
        b.three_point_field_goals_made, b.three_point_field_goals_attempted,
        b.free_throws_made, b.free_throws_attempted,
        b.offensive_rebounds, b.defensive_rebounds, b.total_rebounds,
        b.assists, b.steals, b.blocks, b.total_turnovers,
        b.fouls, b.team_score, NULL::DOUBLE,
        'espn'
    FROM sdv.espn_nba_team_boxscores b
    JOIN nba.games g ON g.espn_game_id = b.game_id
    JOIN nba.team_seasons t ON t.season = g.season AND t.espn_team_id = b.team_id
    WHERE g.source IN ('fte', 'espn')
)
SELECT * FROM nba
UNION ALL
SELECT * FROM espn
