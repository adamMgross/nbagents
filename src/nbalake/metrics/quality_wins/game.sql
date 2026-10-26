-- Quality wins per player per NBA and BAA regular-season game from 1947: quality_win_team_game split among the players by share. From 1994 only players who played that game share it, by seconds times regular-season win shares per minute when shares is win_shares, or by seconds alone when shares is minutes. Before 1994 the season's win shares, or minutes, stand in for each game.
-- example: from quality_win_game() where season = 2016 and player_id = 201939 order by credit desc limit 5
CREATE OR REPLACE TEMP MACRO quality_win_game(shares := 'win_shares') AS TABLE
WITH args AS (
    SELECT CASE WHEN shares IN ('win_shares', 'minutes') THEN shares
                ELSE error('shares is win_shares or minutes, not ' || shares) END AS shares
),
team_credit AS (
    SELECT t.* FROM args a CROSS JOIN quality_win_team_game() t
),
regular AS (
    SELECT s.season, s.team_id, s.player_id, sum(s.ws)::DOUBLE AS ws, sum(s.mp)::DOUBLE AS mp
    FROM args a
    JOIN nba.player_seasons s ON s.lg IN ('NBA', 'BAA') AND s.team_id IS NOT NULL
    GROUP BY ALL
),
played AS (
    SELECT b.game_id, b.team_id, b.player_id, 'game minutes' AS share_basis, r.ws AS regular_ws,
           b.seconds::DOUBLE AS seconds,
           b.seconds * greatest(coalesce(r.ws / nullif(r.mp, 0), 0), 0) AS ws_weight
    FROM args a
    JOIN nba.player_box b ON b.played AND b.player_id IS NOT NULL AND b.seconds > 0
    JOIN team_credit t ON t.game_id = b.game_id AND t.team_id = b.team_id
    LEFT JOIN regular r ON r.season = t.season AND r.team_id = b.team_id AND r.player_id = b.player_id
    WHERE t.season >= 1994
    UNION ALL
    SELECT t.game_id, t.team_id, r.player_id, 'season totals', r.ws, 60 * r.mp,
           greatest(coalesce(r.ws, 0), 0)
    FROM regular r
    JOIN team_credit t ON t.season = r.season AND t.team_id = r.team_id
    WHERE r.season < 1994
),
weights AS (
    SELECT p.*, CASE a.shares WHEN 'win_shares' THEN p.ws_weight ELSE p.seconds END AS weight
    FROM played p
    CROSS JOIN args a
)
SELECT c.season, c.game_id, c.game_date, c.team_id, c.opponent_team_id, w.player_id, c.won,
       c.opponent_elo, c.average_win_prob, c.difficulty, c.credit AS team_credit,
       w.share_basis, w.regular_ws, w.seconds,
       coalesce(w.weight / nullif(sum(w.weight) OVER side, 0),
                w.seconds / nullif(sum(w.seconds) OVER side, 0),
                1 / count(*) OVER side) AS share,
       c.credit * share AS credit
FROM team_credit c
JOIN weights w ON w.game_id = c.game_id AND w.team_id = c.team_id
WINDOW side AS (PARTITION BY w.game_id, w.team_id)
