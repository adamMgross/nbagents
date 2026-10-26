-- Postseason achievement per team per NBA playoff game from first_season: the win minus the chance a baseline playoff team wins that game against the same opponent at the same venue, times the round weight. baseline is weakest or average. rounds is linear (the round number), from_final (4 for the Finals, one less each round before), or flat.
-- example: from postseason_team_credit() where season = 2016 and round = 4 and team_id = 1610612739
CREATE OR REPLACE TEMP MACRO postseason_team_credit(baseline := 'weakest', rounds := 'linear', first_season := 1984) AS TABLE
WITH args AS (
    SELECT CASE WHEN baseline IN ('weakest', 'average') THEN baseline
                ELSE error('baseline is weakest or average, not ' || baseline) END AS baseline,
           CASE WHEN rounds IN ('linear', 'from_final', 'flat') THEN rounds
                ELSE error('rounds is linear, from_final, or flat, not ' || rounds) END AS rounds,
           first_season AS first_season
),
series_games AS (
    SELECT s.season, s.round, s.series_id, unnest(s.game_ids) AS game_id
    FROM args a
    JOIN nba.playoff_series s ON s.lg = 'NBA' AND s.season >= a.first_season
),
bracket AS (
    SELECT season,
           CASE WHEN season = max(season) OVER ()
                THEN greatest(max(round), lag(max(round)) OVER (ORDER BY season))
                ELSE max(round) END AS rounds_in_season
    FROM series_games
    GROUP BY season
),
team_side AS (
    SELECT sg.season, sg.round, sg.series_id, t.game_id, t.game_date, t.team_id,
           t.opponent_team_id, t.won,
           coalesce(t.elo_fit_pre, t.elo_pre) AS elo,
           coalesce(o.elo_fit_pre, o.elo_pre) AS opponent_elo,
           CASE WHEN g.neutral_site THEN 0
                WHEN t.elo_fit_pre IS NOT NULL THEN e.fit_edge
                ELSE 100 END * CASE WHEN t.is_home THEN 1 ELSE -1 END AS venue_edge
    FROM series_games sg
    JOIN nba.games g ON g.game_id = sg.game_id
    JOIN nba.team_games t ON t.game_id = sg.game_id
    JOIN nba.team_games o ON o.game_id = t.game_id AND o.team_id = t.opponent_team_id
    LEFT JOIN nba.team_elo e ON e.game_id = g.game_id AND e.team_id = g.home_team_id
),
baselines AS (
    SELECT season, min(entry_elo) AS weakest, avg(entry_elo) AS average
    FROM (
        SELECT season, team_id, arg_min(elo, (game_date, game_id)) AS entry_elo
        FROM team_side
        GROUP BY ALL
    )
    GROUP BY ALL
)
SELECT t.*,
       CASE a.baseline WHEN 'weakest' THEN b.weakest ELSE b.average END AS baseline_elo,
       elo_game_prob(baseline_elo, t.opponent_elo, t.venue_edge) AS baseline_win_prob,
       CASE a.rounds WHEN 'linear' THEN t.round
                     WHEN 'from_final' THEN 4 - k.rounds_in_season + t.round
                     ELSE 1 END AS round_weight,
       (t.won::INTEGER - baseline_win_prob) * round_weight AS team_credit
FROM team_side t
JOIN baselines b USING (season)
JOIN bracket k USING (season)
CROSS JOIN args a
