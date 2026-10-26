WITH v3 AS (
    SELECT
        season, game_id, action_number,
        CASE WHEN description LIKE '%STEAL%' THEN 'steal'
             WHEN description LIKE '%BLOCK%' THEN 'block' END AS role,
        nullif(person_id, 0) AS player_id
    FROM sdv.nba_stats_pbp
    WHERE action_type = ''
),
v2 AS (
    SELECT DISTINCT
        season::BIGINT AS season, lpad(GAME_ID::VARCHAR, 10, '0') AS game_id, EVENTNUM AS action_number,
        CASE EVENTMSGTYPE WHEN 1 THEN 'assist' WHEN 6 THEN 'fouled' END AS role,
        PLAYER2_ID AS player_id
    FROM shuf.nbastats
    WHERE EVENTMSGTYPE IN (1, 6) AND PLAYER2_ID <> 0 AND PLAYER2_ID NOT BETWEEN 1610612737 AND 1610612766
),
cdn AS (
    SELECT season::BIGINT AS season, lpad(gameId::VARCHAR, 10, '0') AS game_id, actionNumber AS action_number,
           unnest(['assist', 'block', 'steal', 'fouled']) AS role,
           unnest([nullif(assistPersonId, 0), nullif(blockPersonId, 0),
                   nullif(stealPersonId, 0), nullif(foulDrawnPersonId, 0)]) AS player_id
    FROM shuf.cdnnba
),
roles AS (
    SELECT *, 1 AS source_rank FROM v3 WHERE role IS NOT NULL AND player_id IS NOT NULL
    UNION ALL
    SELECT *, 1 AS source_rank FROM v2
    UNION ALL
    SELECT *, 2 AS source_rank FROM cdn WHERE player_id IS NOT NULL
)
SELECT
    season, game_id, action_number,
    arg_min(player_id, source_rank) FILTER (WHERE role = 'assist') AS assist_player_id,
    arg_min(player_id, source_rank) FILTER (WHERE role = 'block') AS block_player_id,
    arg_min(player_id, source_rank) FILTER (WHERE role = 'steal') AS steal_player_id,
    arg_min(player_id, source_rank) FILTER (WHERE role = 'fouled') AS fouled_player_id
FROM roles
GROUP BY season, game_id, action_number
