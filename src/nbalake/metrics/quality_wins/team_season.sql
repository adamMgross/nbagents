-- Quality wins per NBA and BAA team per regular season from first_season: quality_win_team_game summed, beside the plain record, with the rank among that season's teams.
-- example: from quality_win_team_season() where season = 2014 order by rank
CREATE OR REPLACE TEMP MACRO quality_win_team_season(first_season := 1947) AS TABLE
WITH totals AS (
    SELECT season, team_id, count(*) AS games, count(*) FILTER (WHERE won) AS wins,
           sum(credit) AS quality_wins
    FROM quality_win_team_game(first_season := first_season)
    GROUP BY season, team_id
)
SELECT t.season, t.team_id, s.name AS team, t.games, t.wins, t.quality_wins,
       t.quality_wins - t.wins AS above_record,
       rank() OVER (PARTITION BY t.season ORDER BY t.quality_wins DESC) AS rank
FROM totals t
LEFT JOIN nba.team_seasons s ON s.season = t.season AND s.team_id = t.team_id
ORDER BY t.season, rank
