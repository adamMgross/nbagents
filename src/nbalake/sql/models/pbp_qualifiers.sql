WITH parsed AS (
    SELECT
        season,
        lpad(gameId::VARCHAR, 10, '0') AS game_id,
        actionNumber AS action_number,
        list_filter(
            list_transform(string_split(coalesce(qualifiers, ''), ','), lambda q: trim(q)),
            lambda q: q <> ''
        ) AS qualifiers,
        nullif(descriptor, '') AS descriptor,
        nullif(officialId, 0) AS official_id,
        timeActual AS wall_clock
    FROM shuf.cdnnba
)
SELECT
    season, game_id, action_number, qualifiers,
    list_contains(qualifiers, 'fastbreak') AS fast_break,
    list_contains(qualifiers, '2ndchance') AS second_chance,
    list_contains(qualifiers, 'fromturnover') AS from_turnover,
    list_contains(qualifiers, 'pointsinthepaint') AS points_in_paint,
    descriptor, official_id, wall_clock
FROM parsed
