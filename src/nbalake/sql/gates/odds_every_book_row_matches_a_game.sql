SELECT DISTINCT b.game_id, b.book_name
FROM (
    SELECT game_id, book_name FROM odds.book_spreads
    UNION SELECT game_id, book_name FROM odds.book_totals
    UNION SELECT game_id, book_name FROM odds.book_moneylines
) b
ANTI JOIN nba.game_lines l ON l.game_id = b.game_id AND l.book = b.book_name
