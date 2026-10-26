-- Basic postseason achievement per player per playoff run from first_season: the team's postseason_team_credit for the run, rounds counted back from the Finals, times 5 times the player's share of the team's positive regular-season win shares.
-- example: from postseason_basic_season_credit() where season = 1965 order by credit desc limit 10
CREATE OR REPLACE TEMP MACRO postseason_basic_season_credit(baseline := 'weakest', rounds := 'from_final', first_season := 1958) AS TABLE
WITH runs AS (
    SELECT season, team_id, count(*) AS games, max(round) AS last_round, sum(team_credit) AS team_credit
    FROM postseason_team_credit(baseline := baseline, rounds := rounds, first_season := first_season)
    GROUP BY ALL
),
win_shares AS (
    SELECT season, team_id, player_id, sum(ws) AS ws
    FROM nba.player_seasons
    WHERE lg = 'NBA' AND team_id IS NOT NULL
    GROUP BY ALL
)
SELECT r.season, r.team_id, w.player_id, p.name AS player, r.games, r.last_round, w.ws,
       greatest(w.ws, 0) / sum(greatest(w.ws, 0)) OVER (PARTITION BY r.season, r.team_id) AS share,
       r.team_credit, 5 * r.team_credit * share AS credit
FROM runs r
JOIN win_shares w ON w.season = r.season AND w.team_id = r.team_id
LEFT JOIN nba.players p ON p.player_id = w.player_id
