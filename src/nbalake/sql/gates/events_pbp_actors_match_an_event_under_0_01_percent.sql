WITH counted AS (
    SELECT
        (SELECT count(*) FROM nba.pbp_actors a
         ANTI JOIN sdv.nba_stats_pbp p USING (season, game_id, action_number)) AS unmatched,
        (SELECT count(*) FROM nba.pbp_actors) AS actors
)
SELECT unmatched, actors FROM counted WHERE unmatched > 0.0001 * actors
