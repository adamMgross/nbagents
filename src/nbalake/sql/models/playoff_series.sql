WITH RECURSIVE
played AS (
    SELECT g.season, g.lg, g.game_id, g.game_date, g.home_team_id, g.winner_team_id, g.neutral_site,
           least(g.home_team_id, g.away_team_id) AS team_lo,
           greatest(g.home_team_id, g.away_team_id) AS team_hi
    FROM nba.games g
    WHERE g.season_type = 'playoffs' AND g.winner_team_id IS NOT NULL
),
latest AS (
    SELECT max(season) AS season FROM played
),
pairs AS (
    SELECT p.season, p.lg, p.team_lo, p.team_hi,
           p.season = any_value(l.season) AS in_latest,
           arg_min(p.home_team_id, (p.game_date, p.game_id)) AS home_court_team_id,
           arg_min(p.game_id, (p.game_date, p.game_id)) AS first_game_id,
           count(*) AS games,
           count(*) FILTER (WHERE p.winner_team_id = p.team_lo) AS lo_wins,
           count(*) FILTER (WHERE p.winner_team_id = p.team_hi) AS hi_wins,
           min(p.game_date) AS first_game_date,
           max(p.game_date) AS last_game_date,
           list(p.game_id ORDER BY p.game_date, p.game_id) AS game_ids
    FROM played p, latest l
    GROUP BY p.season, p.lg, p.team_lo, p.team_hi, l.season
    HAVING count(*) > 1 OR p.season = any_value(l.season)
),
ordinals AS (
    SELECT season, lg, team_lo, team_hi, max(ordinal) AS ordinal
    FROM (
        SELECT *, row_number() OVER (PARTITION BY season, lg, team_id ORDER BY first_game_date) AS ordinal
        FROM (
            SELECT season, lg, team_lo, team_hi, team_lo AS team_id, first_game_date FROM pairs
            UNION ALL
            SELECT season, lg, team_lo, team_hi, team_hi, first_game_date FROM pairs
        )
    )
    GROUP BY ALL
),
sized AS (
    SELECT p.*, o.ordinal, greatest(p.lo_wins, p.hi_wins) AS max_wins
    FROM pairs p JOIN ordinals o USING (season, lg, team_lo, team_hi)
),
prior_format AS (
    SELECT season + 1 AS season, lg, ordinal, max(max_wins) AS need
    FROM sized
    GROUP BY ALL
),
outcomes AS (
    SELECT *,
           CASE WHEN lo_wins = need AND hi_wins < need THEN team_lo
                WHEN hi_wins = need AND lo_wins < need THEN team_hi END AS winner_team_id,
           CASE WHEN lo_wins = need AND hi_wins < need THEN team_hi
                WHEN hi_wins = need AND lo_wins < need THEN team_lo END AS loser_team_id,
           games <= 2 * need - 1 AND least(lo_wins, hi_wins) < need AS consistent
    FROM (
        SELECT s.*,
               CASE WHEN s.in_latest THEN greatest(s.max_wins, coalesce(f.need, s.max_wins))
                    ELSE s.max_wins END AS need
        FROM sized s LEFT JOIN prior_format f USING (season, lg, ordinal)
    )
),
named AS (
    SELECT o.*,
           CASE WHEN o.home_court_team_id = o.team_lo THEN o.team_hi ELSE o.team_lo END AS other_team_id,
           concat_ws('-', o.season, lower(o.lg), lower(hs.abbreviation), lower(os.abbreviation)) AS series_id,
           CASE WHEN hs.conference = os.conference THEN hs.conference END AS conference
    FROM outcomes o
    JOIN nba.team_seasons hs ON hs.season = o.season AND hs.team_id = o.home_court_team_id
    JOIN nba.team_seasons os ON os.season = o.season
        AND os.team_id = CASE WHEN o.home_court_team_id = o.team_lo THEN o.team_hi ELSE o.team_lo END
),
linked AS (
    SELECT s.*,
           (SELECT n.series_id FROM named n
            WHERE n.season = s.season AND n.lg = s.lg AND n.first_game_date > s.first_game_date
              AND s.winner_team_id IN (n.team_lo, n.team_hi)
            ORDER BY n.first_game_date LIMIT 1) AS next_series_id
    FROM named s
),
covered AS (
    SELECT season, lg
    FROM linked
    GROUP BY ALL
    HAVING bool_and(consistent)
       AND count(loser_team_id) = count(DISTINCT loser_team_id)
       AND (any_value(in_latest) OR count(*) FILTER (WHERE next_series_id IS NULL) = 1)
),
chains AS (
    SELECT series_id AS origin, next_series_id AS reached, 0 AS hops
    FROM linked JOIN covered USING (season, lg)
    UNION ALL
    SELECT c.origin, l.next_series_id, c.hops + 1
    FROM chains c JOIN linked l ON l.series_id = c.reached
),
rounds AS (
    SELECT l.series_id,
           CASE WHEN count(*) FILTER (WHERE l.next_series_id IS NULL) OVER w = 1
                THEN max(d.depth) OVER w + 1 - d.depth
                ELSE l.ordinal END AS round
    FROM linked l
    JOIN (SELECT origin AS series_id, max(hops) AS depth FROM chains GROUP BY 1) d USING (series_id)
    WINDOW w AS (PARTITION BY l.season, l.lg)
),
rated AS (
    SELECT l.*, r.round,
           string_agg(CASE WHEN g.neutral_site THEN 'N' WHEN g.home_team_id = l.home_court_team_id THEN 'H' ELSE 'A' END,
                      '' ORDER BY g.game_date, g.game_id) OVER (PARTITION BY l.series_id) AS venues,
           h.elo_pre AS home_court_elo, a.elo_pre AS other_elo,
           CASE WHEN f.neutral_site THEN 0 ELSE 100 END AS home_edge,
           h.elo_fit_pre AS home_court_elo_fit, a.elo_fit_pre AS other_elo_fit,
           CASE WHEN f.neutral_site THEN 0 ELSE e.fit_edge END AS fit_home_edge
    FROM linked l
    JOIN rounds r USING (series_id)
    JOIN played g ON g.season = l.season AND g.lg = l.lg AND g.team_lo = l.team_lo AND g.team_hi = l.team_hi
    JOIN nba.games f ON f.game_id = l.first_game_id
    LEFT JOIN nba.team_games h ON h.game_id = l.first_game_id AND h.team_id = l.home_court_team_id
    LEFT JOIN nba.team_games a ON a.game_id = l.first_game_id AND a.team_id = l.other_team_id
    LEFT JOIN nba.team_elo e ON e.game_id = l.first_game_id AND e.team_id = l.home_court_team_id
    QUALIFY g.game_id = l.first_game_id
),
games_won AS (
    SELECT r.*,
           1 / (1 + pow(10, -(home_court_elo - other_elo + home_edge) / 400)) AS p_home,
           1 / (1 + pow(10, -(home_court_elo - other_elo - home_edge) / 400)) AS p_road,
           1 / (1 + pow(10, -(home_court_elo_fit - other_elo_fit + fit_home_edge) / 400)) AS p_home_fit,
           1 / (1 + pow(10, -(home_court_elo_fit - other_elo_fit - fit_home_edge) / 400)) AS p_road_fit
    FROM rated r
)
SELECT
    series_id, season, lg, round, conference,
    home_court_team_id, other_team_id, winner_team_id,
    2 * need - 1 AS best_of,
    CASE WHEN home_court_team_id = team_lo THEN lo_wins ELSE hi_wins END AS home_court_wins,
    CASE WHEN home_court_team_id = team_lo THEN hi_wins ELSE lo_wins END AS other_wins,
    games, venues, first_game_date, last_game_date, game_ids,
    home_court_elo, other_elo, home_edge,
    list_sum([
        pow(p_home, bit_count(m & ((1 << need) - 1)))
            * pow(1 - p_home, need - bit_count(m & ((1 << need) - 1)))
            * pow(p_road, bit_count(m >> need))
            * pow(1 - p_road, need - 1 - bit_count(m >> need))
        FOR m IN range(1 << (2 * need - 1)) IF bit_count(m) >= need
    ]) AS home_court_series_prob,
    home_court_elo_fit, other_elo_fit, fit_home_edge,
    list_sum([
        pow(p_home_fit, bit_count(m & ((1 << need) - 1)))
            * pow(1 - p_home_fit, need - bit_count(m & ((1 << need) - 1)))
            * pow(p_road_fit, bit_count(m >> need))
            * pow(1 - p_road_fit, need - 1 - bit_count(m >> need))
        FOR m IN range(1 << (2 * need - 1)) IF bit_count(m) >= need
    ]) AS home_court_series_prob_fit,
    next_series_id
FROM games_won
