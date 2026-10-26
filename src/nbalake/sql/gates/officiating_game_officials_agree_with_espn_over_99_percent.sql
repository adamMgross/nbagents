WITH espn AS (
    SELECT g.game_id, regexp_replace(lower(e.official_display_name), '[^a-z]', '', 'g') AS full_name
    FROM sdv.espn_nba_officials e
    JOIN nba.games g ON g.espn_game_id = e.game_id
),
nba AS (
    SELECT o.game_id, regexp_replace(lower(o.last_name), '[^a-z]', '', 'g') AS last_name
    FROM nba.game_officials o
    SEMI JOIN espn USING (game_id)
),
counted AS (
    SELECT
        count(*) FILTER (WHERE NOT EXISTS (
            SELECT 1 FROM espn e WHERE e.game_id = n.game_id AND ends_with(e.full_name, n.last_name)
        )) AS unnamed,
        count(*) AS officials
    FROM nba n
)
SELECT unnamed, officials FROM counted WHERE unnamed > 0.01 * officials
