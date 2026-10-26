-- Quality wins per team per NBA and BAA regular-season game from first_season: a win counts the chance a team of the season's average Elo would have lost the same game, against the same opponent at the same venue, scaled so the season's average win counts 1. A loss counts 0, and a win with no Elo counts 1.
-- example: from quality_win_team_game() where season = 2016 and team_id = 1610612744 order by credit desc limit 5
CREATE OR REPLACE TEMP MACRO quality_win_team_game(first_season := 1947) AS TABLE
WITH args AS (
    SELECT first_season AS first_season
),
side AS (
    SELECT g.season, g.game_id, t.game_date, t.team_id, t.opponent_team_id, t.is_home, t.won,
           coalesce(t.elo_fit_pre, t.elo_pre) AS elo,
           coalesce(o.elo_fit_pre, o.elo_pre) AS opponent_elo,
           CASE WHEN g.neutral_site THEN 0
                WHEN t.elo_fit_pre IS NOT NULL THEN e.fit_edge
                ELSE 100 END * CASE WHEN t.is_home THEN 1 ELSE -1 END AS venue_edge
    FROM args a
    JOIN nba.games g ON g.season >= a.first_season AND g.season_type = 'regular'
                    AND g.lg IN ('NBA', 'BAA')
    JOIN nba.team_games t ON t.game_id = g.game_id
    JOIN nba.team_games o ON o.game_id = t.game_id AND o.team_id = t.opponent_team_id
    LEFT JOIN nba.team_elo e ON e.game_id = g.game_id AND e.team_id = g.home_team_id
),
priced AS (
    SELECT *,
           avg(elo) OVER (PARTITION BY season) AS average_elo,
           elo_game_prob(average_elo, opponent_elo, venue_edge) AS average_win_prob
    FROM side
)
SELECT *,
       coalesce((1 - average_win_prob)
           / avg(1 - average_win_prob) FILTER (WHERE won) OVER (PARTITION BY season), 1) AS difficulty,
       CASE WHEN won THEN difficulty ELSE 0 END AS credit
FROM priced
