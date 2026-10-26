-- One team's games in a season with opponent, result, rest, Elo (FiveThirtyEight's through 2014-15, the lake's own after), the median closing spread, and the result against it. season_type NULL means every type, including preseason.
-- example: from team_games_of(1610612744, 2016)
CREATE OR REPLACE TEMP MACRO team_games_of(team_id, season, season_type := 'regular') AS TABLE
WITH args AS (
    SELECT team_id AS team_id, season AS season, season_type AS season_type
),
lines AS (
    SELECT l.game_id, median(l.home_spread) AS home_spread, median(l.total) AS total
    FROM nba.game_lines l
    GROUP BY 1
),
picked AS (
    SELECT
        tg.*,
        ts.abbreviation AS team, os.abbreviation AS opponent,
        CASE WHEN tg.is_home THEN ln.home_spread ELSE -ln.home_spread END AS spread,
        ln.total
    FROM args a
    JOIN nba.team_games tg ON tg.team_id = a.team_id AND tg.season = a.season
    LEFT JOIN nba.team_seasons ts ON ts.season = tg.season AND ts.team_id = tg.team_id
    LEFT JOIN nba.team_seasons os ON os.season = tg.season AND os.team_id = tg.opponent_team_id
    LEFT JOIN lines ln ON ln.game_id = tg.game_id
    WHERE a.season_type IS NULL OR tg.season_type = a.season_type
)
SELECT
    p.game_date, p.season, p.season_type, p.game_id, p.team_id, p.team, p.opponent_team_id,
    p.opponent, p.is_home, p.won, p.pts, p.opp_pts, p.margin, p.season_game_number,
    p.rest_days, p.back_to_back, p.elo_pre, p.elo_win_prob, p.spread, p.total,
    CASE
        WHEN p.spread IS NULL OR p.margin IS NULL THEN NULL
        WHEN p.margin + p.spread > 0 THEN 'cover'
        WHEN p.margin + p.spread < 0 THEN 'loss'
        ELSE 'push'
    END AS ats
FROM picked p
ORDER BY p.game_date, p.game_id;
