WITH bref AS (
    SELECT season, player_id, pts
    FROM nba.player_seasons
    QUALIFY row_number() OVER (PARTITION BY season, player_id ORDER BY multi_team DESC) = 1
),
counted AS (
    SELECT count(*) FILTER (WHERE abs(d.pts - b.pts) > 2) AS off, count(*) AS player_seasons
    FROM nba.player_season_dash d
    JOIN bref b USING (season, player_id)
    WHERE d.season_type = 'regular'
)
SELECT off, player_seasons FROM counted WHERE off > 0.001 * player_seasons
