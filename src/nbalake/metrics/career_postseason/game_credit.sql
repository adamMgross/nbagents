-- Postseason achievement per player per NBA playoff game from 1984: postseason_team_credit times 5 times the player's share, his minutes weighted by regular-season BPM plus, from 1994, an adjustment for how his box production that postseason beat his regular season. baseline is weakest or average, rounds is linear or flat, playoff_adjustment false gives version 1.
-- example: from postseason_game_credit() where season = 2019 and player_id = 202695 order by game_date limit 5
CREATE OR REPLACE TEMP MACRO postseason_game_credit(baseline := 'weakest', rounds := 'linear', playoff_adjustment := true) AS TABLE
WITH team_credit AS (
    FROM postseason_team_credit(baseline := baseline, rounds := rounds)
),
args AS (
    SELECT playoff_adjustment AS playoff_adjustment
),
regular AS (
    SELECT season, team_id, player_id, max(bpm)::DOUBLE AS bpm, sum(mp)::DOUBLE AS mp
    FROM nba.player_seasons
    WHERE lg = 'NBA' AND team_id IS NOT NULL AND season >= 1984
    GROUP BY ALL
),
production AS (
    SELECT b.season, b.team_id, b.player_id,
           sum(b.seconds) FILTER (WHERE g.season_type = 'playoffs') / 60 AS playoff_minutes,
           2160 * sum(b.game_score) FILTER (WHERE g.season_type = 'playoffs')
               / sum(b.seconds) FILTER (WHERE g.season_type = 'playoffs')
             - 2160 * sum(b.game_score) FILTER (WHERE g.season_type = 'regular')
               / sum(b.seconds) FILTER (WHERE g.season_type = 'regular') AS game_score_gain
    FROM (
        SELECT *, pts + 0.4 * fgm - 0.7 * fga - 0.4 * (fta - ftm) + 0.7 * oreb + 0.3 * dreb
                  + coalesce(stl, 0) + 0.7 * ast + 0.7 * coalesce(blk, 0) - 0.4 * pf - tov AS game_score
        FROM nba.player_box
        WHERE season >= 1994 AND played AND player_id IS NOT NULL AND seconds > 0
    ) b
    JOIN nba.games g ON g.game_id = b.game_id AND g.season_type IN ('regular', 'playoffs')
    GROUP BY ALL
    HAVING sum(b.seconds) FILTER (WHERE g.season_type = 'playoffs') > 0
       AND sum(b.seconds) FILTER (WHERE g.season_type = 'regular') >= 60 * 500
),
adjustments AS (
    SELECT p.season, p.team_id, p.player_id,
           CASE WHEN a.playoff_adjustment THEN
               0.6 * (p.game_score_gain
                      - sum(p.game_score_gain * p.playoff_minutes) OVER (PARTITION BY p.season)
                        / sum(p.playoff_minutes) OVER (PARTITION BY p.season))
                   * p.playoff_minutes / (p.playoff_minutes + 750)
               ELSE 0 END AS playoff_bpm_adjustment
    FROM production p
    CROSS JOIN args a
),
weights AS (
    SELECT b.game_id, b.team_id, b.player_id, 'playoff minutes' AS share_basis, r.bpm AS regular_bpm,
           coalesce(j.playoff_bpm_adjustment, 0) AS playoff_bpm_adjustment,
           b.seconds::DOUBLE AS seconds,
           b.seconds * greatest(coalesce(r.bpm, -2) + coalesce(j.playoff_bpm_adjustment, 0) + 2, 0) AS weight
    FROM nba.player_box b
    JOIN team_credit t ON t.game_id = b.game_id AND t.team_id = b.team_id
    LEFT JOIN regular r ON r.season = t.season AND r.team_id = b.team_id AND r.player_id = b.player_id
    LEFT JOIN adjustments j ON j.season = t.season AND j.team_id = b.team_id AND j.player_id = b.player_id
    WHERE t.season >= 1994 AND b.played AND b.player_id IS NOT NULL
    UNION ALL
    SELECT t.game_id, t.team_id, r.player_id, 'regular season minutes', r.bpm, 0,
           60 * r.mp, r.mp * greatest(coalesce(r.bpm, -2) + 2, 0)
    FROM regular r
    JOIN team_credit t ON t.season = r.season AND t.team_id = r.team_id
    WHERE r.season < 1994 AND r.mp > 0
)
SELECT c.season, c.round, c.series_id, c.game_id, c.game_date, c.team_id, c.opponent_team_id,
       w.player_id, c.won, c.elo, c.opponent_elo, c.baseline_elo, c.venue_edge, c.baseline_win_prob,
       c.round_weight, c.team_credit, w.share_basis, w.regular_bpm, w.playoff_bpm_adjustment,
       coalesce(w.weight / nullif(sum(w.weight) OVER side, 0), w.seconds / sum(w.seconds) OVER side) AS share,
       5 * c.team_credit * share AS credit
FROM team_credit c
JOIN weights w ON w.game_id = c.game_id AND w.team_id = c.team_id
WINDOW side AS (PARTITION BY w.game_id, w.team_id)
