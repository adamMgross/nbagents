-- A player's game log with date, team, opponent, home, result, score, minutes, box line, and the median closing spread for his team. Games he did not play are left out unless include_dnp. season and season_type NULL mean all.
-- example: from player_games(201939, 2016)
CREATE OR REPLACE TEMP MACRO player_games(player_id, season := NULL, season_type := 'regular', include_dnp := false) AS TABLE
WITH args AS (
    SELECT player_id AS player_id, season AS season, season_type AS season_type,
           include_dnp AS include_dnp
),
lines AS (
    SELECT l.game_id, median(l.home_spread) AS home_spread
    FROM nba.game_lines l
    GROUP BY 1
)
SELECT
    g.game_date, g.season, g.season_type, b.game_id,
    b.team_id, ts.abbreviation AS team,
    CASE WHEN b.team_id = g.home_team_id THEN g.away_team_id ELSE g.home_team_id END
        AS opponent_team_id,
    os.abbreviation AS opponent,
    b.team_id = g.home_team_id AS home,
    CASE WHEN g.winner_team_id IS NOT NULL THEN g.winner_team_id = b.team_id END AS won,
    CASE WHEN b.team_id = g.home_team_id THEN g.home_pts ELSE g.away_pts END AS team_pts,
    CASE WHEN b.team_id = g.home_team_id THEN g.away_pts ELSE g.home_pts END AS opp_pts,
    round(b.seconds / 60.0, 1) AS minutes,
    b.pts, b.reb, b.ast, b.stl, b.blk, b.tov, b.fgm, b.fga, b.fg3m, b.fg3a, b.ftm, b.fta,
    b.oreb, b.dreb, b.pf, b.plus_minus, b.started, b.played, b.dnp_reason,
    CASE WHEN b.team_id = g.home_team_id THEN ln.home_spread ELSE -ln.home_spread END AS spread
FROM args a
JOIN nba.player_box b ON b.player_id = a.player_id
JOIN nba.games g ON g.game_id = b.game_id
LEFT JOIN nba.team_seasons ts ON ts.season = g.season AND ts.team_id = b.team_id
LEFT JOIN nba.team_seasons os ON os.season = g.season
    AND os.team_id = CASE WHEN b.team_id = g.home_team_id THEN g.away_team_id ELSE g.home_team_id END
LEFT JOIN lines ln ON ln.game_id = b.game_id
WHERE (a.season IS NULL OR g.season = a.season)
  AND (a.include_dnp OR b.played)
  AND (a.season_type IS NULL OR g.season_type = a.season_type)
ORDER BY g.game_date, b.game_id;
