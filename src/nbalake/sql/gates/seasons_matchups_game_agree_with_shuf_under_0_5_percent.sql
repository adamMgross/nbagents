WITH shuf AS (
    SELECT lpad(game_id::VARCHAR, 10, '0') AS game_id, person_id AS off_player_id,
           matchups_person_id AS def_player_id, partial_possessions
    FROM shuf.matchups
),
counted AS (
    SELECT
        count(*) FILTER (WHERE s.game_id IS NULL
                         OR abs(m.partial_possessions - s.partial_possessions) > 0.5) AS off,
        count(*) AS matchups
    FROM nba.matchups_game m
    LEFT JOIN shuf s USING (game_id, off_player_id, def_player_id)
    WHERE m.game_id IN (SELECT game_id FROM shuf)
)
SELECT off, matchups FROM counted WHERE off > 0.005 * matchups
