WITH played AS (
    SELECT DISTINCT
        c.player_id,
        regexp_replace(lower(strip_accents(c.last_name)), '[^a-z]', '', 'g') AS last_name,
        regexp_replace(lower(strip_accents(p.name)), '[^a-z]', '', 'g') AS name
    FROM nba.draft_combine c
    JOIN nba.players p USING (player_id)
),
counted AS (
    SELECT count(*) FILTER (WHERE NOT contains(name, last_name)) AS mismatched, count(*) AS ids
    FROM played
)
SELECT mismatched, ids FROM counted WHERE mismatched > 0.02 * ids
