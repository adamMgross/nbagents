WITH per_team AS (
    SELECT game_id, team_id, count(*) FILTER (WHERE started) AS starters
    FROM nba.player_box
    WHERE started IS NOT NULL
    GROUP BY ALL
),
counted AS (
    SELECT count(*) FILTER (WHERE starters <> 5) AS off, count(*) AS team_games FROM per_team
)
SELECT off, team_games FROM counted WHERE off > 0.005 * team_games
