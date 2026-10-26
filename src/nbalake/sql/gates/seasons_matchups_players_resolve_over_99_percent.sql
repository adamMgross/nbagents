WITH pairs AS (
    SELECT off_player_id, def_player_id FROM nba.matchups_game
    UNION ALL
    SELECT off_player_id, def_player_id FROM nba.matchups_season
),
counted AS (
    SELECT
        count(*) FILTER (WHERE o.player_id IS NULL OR d.player_id IS NULL) AS unresolved,
        count(*) AS matchups
    FROM pairs
    LEFT JOIN nba.players o ON o.player_id = pairs.off_player_id
    LEFT JOIN nba.players d ON d.player_id = pairs.def_player_id
)
SELECT unresolved, matchups FROM counted WHERE unresolved > 0.01 * matchups
