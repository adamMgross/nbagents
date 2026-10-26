SELECT source, games, favorite_win_rate
FROM (
    SELECT
        l.source,
        count(*) AS games,
        avg(((g.home_pts > g.away_pts) = (l.home_spread < 0))::INTEGER) AS favorite_win_rate
    FROM nba.game_lines l
    JOIN nba.games g USING (game_id)
    WHERE l.home_spread <> 0 AND g.home_pts <> g.away_pts
    GROUP BY l.source
)
WHERE favorite_win_rate NOT BETWEEN 0.60 AND 0.75
