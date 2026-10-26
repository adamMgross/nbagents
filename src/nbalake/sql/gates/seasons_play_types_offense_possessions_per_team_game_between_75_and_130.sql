WITH poss AS (
    SELECT season, team_id, sum(poss) AS poss
    FROM nba.player_season_play_types
    WHERE season_type = 'regular' AND side = 'offense'
      AND season < (SELECT max(season) FROM nba.team_games)
    GROUP BY ALL
),
games AS (
    SELECT season, team_id, count(*) AS games
    FROM nba.team_games
    WHERE season_type = 'regular'
    GROUP BY ALL
)
SELECT season, team_id, round(poss / games, 1) AS per_game
FROM poss JOIN games USING (season, team_id)
WHERE poss / games NOT BETWEEN 75 AND 130
