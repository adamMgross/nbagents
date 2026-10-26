WITH chart AS (
    SELECT game_id, count(*) FILTER (made) AS made FROM nba.shots GROUP BY game_id
),
pbp AS (
    SELECT game_id, count(*) FILTER (shot_result = 'Made' AND is_field_goal = 1) AS made
    FROM nba.pbp
    WHERE game_id IN (SELECT game_id FROM chart)
    GROUP BY game_id
)
SELECT game_id, c.made AS chart_made, p.made AS pbp_made
FROM chart c JOIN pbp p USING (game_id)
WHERE c.made <> p.made
