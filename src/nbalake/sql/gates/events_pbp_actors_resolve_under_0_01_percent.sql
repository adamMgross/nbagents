WITH ids AS (
    SELECT unnest([a.assist_player_id, a.block_player_id, a.steal_player_id, a.fouled_player_id]) AS player_id
    FROM nba.pbp_actors a
    JOIN nba.games g USING (game_id)
    WHERE g.season_type IN ('regular', 'play-in', 'playoffs', 'nba-cup')
),
known AS (
    SELECT DISTINCT source_id FROM nba.player_xref WHERE source = 'nba'
),
counted AS (
    SELECT count(*) AS actor_ids, count(*) FILTER (WHERE k.source_id IS NULL) AS unresolved
    FROM ids LEFT JOIN known k ON k.source_id = ids.player_id::VARCHAR
    WHERE ids.player_id IS NOT NULL
)
SELECT unresolved, actor_ids FROM counted WHERE unresolved > 0.0001 * actor_ids
