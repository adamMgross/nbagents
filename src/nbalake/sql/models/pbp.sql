WITH scored AS (
    SELECT
        * EXCLUDE (_unit, _sha256, _fetched_at, person_id, score_home, score_away, season),
        season,
        CASE WHEN person_id <> 0 AND person_id NOT BETWEEN 1610612737 AND 1610612766 THEN person_id END AS player_id,
        TRY_CAST(nullif(score_home, '') AS INTEGER) AS score_home,
        TRY_CAST(nullif(score_away, '') AS INTEGER) AS score_away,
        CASE WHEN period <= 4 THEN (period - 1) * 720 + 720 - seconds_remaining
             ELSE 2880 + (period - 5) * 300 + 300 - seconds_remaining END AS game_seconds_elapsed,
        abs(
            coalesce(last_value(TRY_CAST(nullif(score_home, '') AS INTEGER) IGNORE NULLS) OVER before, 0)
            - coalesce(last_value(TRY_CAST(nullif(score_away, '') AS INTEGER) IGNORE NULLS) OVER before, 0)
        ) AS margin_before
    FROM sdv.nba_stats_pbp
    WINDOW before AS (PARTITION BY season, game_id ORDER BY order_index ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
)
SELECT
    s.* EXCLUDE (margin_before),
    s.period >= 4 AND (
        s.margin_before >= 30
        OR (s.margin_before >= 25 AND s.seconds_remaining <= 540)
        OR (s.margin_before >= 20 AND s.seconds_remaining <= 360)
    ) AS garbage_time,
    a.assist_player_id, a.block_player_id, a.steal_player_id, a.fouled_player_id,
    q.qualifiers, q.fast_break, q.second_chance, q.from_turnover, q.points_in_paint,
    q.descriptor, q.official_id, q.wall_clock
FROM scored s
LEFT JOIN nba.pbp_actors a
    ON a.season = s.season AND a.game_id = s.game_id AND a.action_number = s.action_number
    AND s.action_type <> ''
LEFT JOIN nba.pbp_qualifiers q
    ON q.season = s.season AND q.game_id = s.game_id AND q.action_number = s.action_number
    AND s.action_type <> ''
