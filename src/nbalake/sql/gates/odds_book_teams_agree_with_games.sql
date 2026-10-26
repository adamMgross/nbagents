SELECT b.game_id, b.book_name, b.team_id, b.a_team_id, g.away_team_id, g.home_team_id
FROM (
    SELECT game_id, book_name, team_id, a_team_id FROM odds.book_spreads
    UNION ALL SELECT game_id, book_name, team_id, a_team_id FROM odds.book_totals
    UNION ALL SELECT game_id, book_name, team_id, a_team_id FROM odds.book_moneylines
) b
JOIN nba.games g ON g.game_id = b.game_id
WHERE TRY_CAST(b.team_id AS BIGINT) IS DISTINCT FROM g.away_team_id
   OR TRY_CAST(b.a_team_id AS BIGINT) IS DISTINCT FROM g.home_team_id
