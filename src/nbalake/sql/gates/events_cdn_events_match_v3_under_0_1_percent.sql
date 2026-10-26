WITH cdn AS (
    SELECT season::BIGINT AS season, lpad(gameId::VARCHAR, 10, '0') AS game_id,
           actionNumber AS action_number, period
    FROM shuf.cdnnba
    WHERE actionType IN ('2pt', '3pt', 'freethrow', 'rebound', 'turnover', 'foul', 'timeout',
                         'violation', 'jumpball', 'period')
),
counted AS (
    SELECT
        count(*) FILTER (WHERE p.game_id IS NULL) AS unmatched,
        count(*) AS events
    FROM cdn c
    LEFT JOIN (SELECT DISTINCT season, game_id, action_number, period FROM sdv.nba_stats_pbp
               WHERE action_type <> '') p
        USING (season, game_id, action_number, period)
)
SELECT unmatched, events FROM counted WHERE unmatched > 0.001 * events
