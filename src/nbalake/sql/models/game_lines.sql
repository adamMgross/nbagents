WITH lines AS (
    SELECT
        g.game_id, g.season, 'kaggle_lines' AS source, NULL::VARCHAR AS book,
        CASE l.whos_favored WHEN 'home' THEN -l.spread ELSE l.spread END::DOUBLE AS home_spread,
        NULL::INTEGER AS home_spread_price, NULL::INTEGER AS away_spread_price,
        l.total::DOUBLE AS total,
        l.moneyline_home::INTEGER AS home_moneyline, l.moneyline_away::INTEGER AS away_moneyline
    FROM odds.lines l
    JOIN nba.odds_teams h ON h.code = l.home
    JOIN nba.odds_teams a ON a.code = l.away
    JOIN nba.games g
        ON g.game_date = l.date AND g.home_team_id = h.team_id AND g.away_team_id = a.team_id
),
book_keys AS (
    SELECT game_id, book_name FROM odds.book_spreads
    UNION
    SELECT game_id, book_name FROM odds.book_totals
    UNION
    SELECT game_id, book_name FROM odds.book_moneylines
),
books AS (
    SELECT
        g.game_id, g.season, 'kaggle_books' AS source, k.book_name AS book,
        TRY_CAST(s.spread2 AS DOUBLE) AS home_spread,
        TRY_CAST(s.price2 AS DOUBLE)::INTEGER AS home_spread_price,
        TRY_CAST(s.price1 AS DOUBLE)::INTEGER AS away_spread_price,
        TRY_CAST(t.total1 AS DOUBLE) AS total,
        TRY_CAST(m.price2 AS DOUBLE)::INTEGER AS home_moneyline,
        TRY_CAST(m.price1 AS DOUBLE)::INTEGER AS away_moneyline
    FROM book_keys k
    JOIN nba.games g ON g.game_id = k.game_id
    LEFT JOIN odds.book_spreads s ON s.game_id = k.game_id AND s.book_name = k.book_name
    LEFT JOIN odds.book_totals t ON t.game_id = k.game_id AND t.book_name = k.book_name
    LEFT JOIN odds.book_moneylines m ON m.game_id = k.game_id AND m.book_name = k.book_name
),
espn AS (
    SELECT
        g.game_id, g.season, 'espn' AS source, NULL::VARCHAR AS book,
        -any_value(p.home_team_spread)::DOUBLE AS home_spread,
        NULL::INTEGER AS home_spread_price, NULL::INTEGER AS away_spread_price,
        NULL::DOUBLE AS total, NULL::INTEGER AS home_moneyline, NULL::INTEGER AS away_moneyline
    FROM sdv.espn_nba_pbp p
    JOIN nba.games g ON g.espn_game_id = p.game_id
    GROUP BY g.game_id, g.season
    HAVING bool_or(p.game_spread_available)
)
SELECT * FROM lines
UNION ALL
SELECT * FROM books
UNION ALL
SELECT * FROM espn
