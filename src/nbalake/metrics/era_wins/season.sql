-- Wins above replacement per NBA player season from 1974, in its own league (wins) and translated into reference_season's league (neutral_wins): that season's talent, free throw whistle, and wins per point.
-- example: from era_wins_season() where season = 1988 order by neutral_wins desc limit 10
CREATE OR REPLACE TEMP MACRO era_wins_season(first_season := 1974, reference_season := 2026) AS TABLE
WITH args AS (
    SELECT CASE WHEN first_season >= 1974 THEN first_season
                ELSE error('first_season must be 1974 or later, when BPM starts') END AS first_season,
           reference_season AS reference_season
),
players AS (
    SELECT s.season, s.player_id, s.player, s.age, s.mp, s.bpm, s.ft, s.fta
    FROM args a
    JOIN nba.player_seasons s
      ON s.lg = 'NBA' AND s.season >= a.first_season AND s.bpm IS NOT NULL AND s.mp > 0
    QUALIFY count(*) OVER (PARTITION BY s.season, s.player_id) = 1 OR s.multi_team
),
league AS (
    SELECT t.season, avg(t.mp) AS team_mp, max(t.g) AS team_games
    FROM args a
    JOIN nba.team_season_stats t ON t.lg = 'NBA' AND t.season >= a.first_season
    GROUP BY t.season
),
pace AS (
    SELECT t.season, avg(t.pace) AS pace
    FROM args a
    JOIN nba.team_seasons t ON t.lg = 'NBA' AND t.season >= a.first_season
    GROUP BY t.season
),
environment AS (
    SELECT e.*, w.wins_per_point, s.strength,
           max(e.two_rate) FILTER (WHERE e.season = a.reference_season) OVER () AS ref_two,
           max(e.and_one_rate) FILTER (WHERE e.season = a.reference_season) OVER () AS ref_and_one,
           max(e.three_rate) FILTER (WHERE e.season = a.reference_season) OVER () AS ref_three,
           max(w.wins_per_point) FILTER (WHERE e.season = a.reference_season) OVER ()
               AS ref_wins_per_point
    FROM args a
    CROSS JOIN free_throw_environment() e
    JOIN wins_per_point() w USING (season)
    JOIN league_strength(reference_season := reference_season) s USING (season)
),
trips AS (
    SELECT p.*, e.*,
           CASE WHEN e.measured THEN coalesce(t.two_trips, 0) ELSE p.fta * e.two_share / 2 END AS two,
           CASE WHEN e.measured THEN coalesce(t.and_ones, 0) ELSE p.fta * e.and_one_share END AS and_one,
           CASE WHEN e.measured THEN coalesce(t.three_trips, 0) ELSE p.fta * e.three_share / 3 END AS three
    FROM players p
    JOIN environment e USING (season)
    LEFT JOIN whistle_trips() t ON t.season = p.season AND t.player_id = p.player_id
),
adjusted AS (
    SELECT t.season, t.player_id, t.player, t.age, t.mp, t.bpm, t.wins_per_point, t.strength,
           t.ref_wins_per_point, l.team_games, t.mp / (l.team_mp / 5) AS minute_share,
           100 * CASE WHEN t.fta > 0 THEN t.ft / t.fta ELSE 0 END
               * (2 * t.two * (t.ref_two / t.two_rate - 1)
                  + t.and_one * (t.ref_and_one / t.and_one_rate - 1)
                  + 3 * t.three * coalesce(t.ref_three / t.three_rate - 1, 0))
               / (t.mp / 48 * c.pace) AS whistle_points
    FROM trips t
    JOIN league l USING (season)
    JOIN pace c USING (season)
),
rules AS (
    SELECT *,
           whistle_points - sum(whistle_points * mp) OVER (PARTITION BY season)
               / sum(mp) OVER (PARTITION BY season) AS whistle_adj
    FROM adjusted
)
SELECT season, player_id, player, age, mp, minute_share, bpm, wins_per_point,
       (bpm + 2) * minute_share * wins_per_point * team_games / 82 AS wins,
       whistle_adj, strength, bpm + whistle_adj + strength AS neutral_bpm,
       (bpm + whistle_adj + strength + 2) * minute_share * ref_wins_per_point AS neutral_wins
FROM rules
ORDER BY season, neutral_wins DESC
