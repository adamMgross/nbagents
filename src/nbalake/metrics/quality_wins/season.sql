-- Quality wins per player per team per NBA and BAA regular season from 1947: quality_win_game summed. games and wins count the games he played from 1994 and are NULL before, when the season totals stand in for each game.
-- example: from quality_win_season() where season = 2016 order by credit desc limit 10
CREATE OR REPLACE TEMP MACRO quality_win_season(shares := 'win_shares') AS TABLE
SELECT c.season, c.team_id, c.player_id, p.name AS player,
       CASE WHEN c.season >= 1994 THEN count(*) END AS games,
       CASE WHEN c.season >= 1994 THEN count(*) FILTER (WHERE c.won) END AS wins,
       sum(c.credit) AS credit
FROM quality_win_game(shares := shares) c
LEFT JOIN nba.players p ON p.player_id = c.player_id
GROUP BY c.season, c.team_id, c.player_id, p.name
