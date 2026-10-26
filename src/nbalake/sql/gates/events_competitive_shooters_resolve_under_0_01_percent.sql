WITH shooting AS (
    SELECT p.player_id
    FROM nba.pbp p
    JOIN nba.games g USING (game_id)
    WHERE g.season_type IN ('regular', 'play-in', 'playoffs', 'nba-cup')
      AND p.event_type IN ('made_shot', 'missed_shot', 'free_throw')
),
counted AS (
    SELECT
        count(*) AS events,
        count(*) FILTER (
            s.player_id IS NULL OR s.player_id::VARCHAR NOT IN (SELECT source_id FROM nba.player_xref WHERE source = 'nba')
        ) AS unresolved
    FROM shooting s
)
SELECT unresolved, events FROM counted WHERE unresolved > 0.0001 * events
