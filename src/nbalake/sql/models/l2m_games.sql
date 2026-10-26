SELECT
    game_id,
    any_value(season) AS season,
    any_value(season_type) AS season_type,
    any_value(game_date) AS game_date,
    count(*) AS calls,
    count(*) FILTER (WHERE decision = 'CC') AS correct_calls,
    count(*) FILTER (WHERE decision = 'IC') AS incorrect_calls,
    count(*) FILTER (WHERE decision = 'CNC') AS correct_non_calls,
    count(*) FILTER (WHERE decision = 'INC') AS incorrect_non_calls,
    any_value(concat_ws(', ', official_1, official_2, official_3, official_4)) AS officials
FROM nba.l2m_calls
GROUP BY game_id
