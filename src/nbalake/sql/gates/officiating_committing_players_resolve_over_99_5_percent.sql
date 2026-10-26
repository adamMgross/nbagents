SELECT unresolved, named
FROM (
    SELECT count(*) FILTER (committing_player_id IS NULL) AS unresolved, count(*) AS named
    FROM nba.l2m_calls
    WHERE committing_name IS NOT NULL AND NOT committing_is_team
)
WHERE unresolved > 0.005 * named
