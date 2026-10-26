WITH
last_team AS (
    SELECT ps.player_id, ts.abbreviation
    FROM nba.player_seasons ps
    JOIN nba.team_seasons ts ON ts.team_id = ps.team_id AND ts.season = ps.season
    QUALIFY row_number() OVER (PARTITION BY ps.player_id ORDER BY ps.season DESC) = 1
),
player_names AS (
    SELECT player_id, name FROM nba.player_xref WHERE name IS NOT NULL
    UNION
    SELECT player_id, alias FROM nba.player_aliases
),
player_alias_keys AS (
    SELECT player_id,
           list(DISTINCT trim(regexp_replace(regexp_replace(lower(strip_accents(name)),
                '[''.]', '', 'g'), '[^a-z0-9]+', ' ', 'g'))) AS aliases
    FROM player_names GROUP BY 1
),
players AS (
    SELECT 'player' AS kind, p.player_id::VARCHAR AS id, p.name AS label,
           trim(regexp_replace(regexp_replace(lower(strip_accents(p.name)),
                '[''.]', '', 'g'), '[^a-z0-9]+', ' ', 'g')) AS key,
           list_filter(coalesce(a.aliases, []), lambda x: x <> key) AS aliases,
           p.from_season AS season_min, p.to_season AS season_max,
           concat_ws(', ', 'last team ' || lt.abbreviation, 'drafted ' || p.draft_year,
                     p.college) AS context
    FROM nba.players p
    LEFT JOIN player_alias_keys a USING (player_id)
    LEFT JOIN last_team lt USING (player_id)
),
team_names AS (
    SELECT ts.team_id, ts.name, min(ts.season) AS season_min, max(ts.season) AS season_max,
           list(DISTINCT lower(ts.abbreviation)) FILTER (WHERE ts.abbreviation IS NOT NULL)
               AS abbreviations
    FROM nba.team_seasons ts WHERE ts.name IS NOT NULL GROUP BY 1, 2
),
team_seed AS (
    SELECT team_id, list(DISTINCT lower(alias)) AS aliases FROM nba.team_aliases GROUP BY 1
),
teams AS (
    SELECT 'team' AS kind, tn.team_id::VARCHAR AS id, tn.name AS label,
           trim(regexp_replace(regexp_replace(lower(strip_accents(tn.name)),
                '[''.]', '', 'g'), '[^a-z0-9]+', ' ', 'g')) AS key,
           list_distinct(list_concat(tn.abbreviations, coalesce(s.aliases, []))) AS aliases,
           tn.season_min, tn.season_max,
           concat_ws(', ', 'team_id ' || tn.team_id,
                     CASE WHEN t.name <> tn.name THEN 'now ' || t.name END) AS context
    FROM team_names tn
    JOIN nba.teams t USING (team_id)
    LEFT JOIN team_seed s USING (team_id)
),
season_names AS (
    SELECT season, team_id, abbreviation, name FROM nba.team_seasons
),
playoff_series AS (
    SELECT game_id,
           row_number() OVER (
               PARTITION BY season, least(home_team_id, away_team_id),
                            greatest(home_team_id, away_team_id)
               ORDER BY game_date, game_id) AS series_game,
           max(game_date) OVER (
               PARTITION BY season, least(home_team_id, away_team_id),
                            greatest(home_team_id, away_team_id)) AS series_end,
           max(game_date) OVER (PARTITION BY season) AS season_end
    FROM nba.games WHERE season_type = 'playoffs'
),
game_rows AS (
    SELECT g.*, h.abbreviation AS home_abbr, a.abbreviation AS away_abbr,
           h.name AS home_name, a.name AS away_name,
           CASE WHEN g.game_id LIKE '004%' AND substr(g.game_id, 8, 1) IN ('1', '2', '3', '4')
                THEN substr(g.game_id, 10, 1)::INTEGER ELSE ps.series_game END AS series_game,
           CASE
               WHEN g.season_type <> 'playoffs' THEN NULL
               WHEN g.game_id LIKE '004%' AND substr(g.game_id, 8, 1) IN ('1', '2', '3', '4') THEN
                   CASE substr(g.game_id, 8, 1)
                       WHEN '1' THEN 'first round' WHEN '2' THEN 'conference semifinals'
                       WHEN '3' THEN 'conference finals' WHEN '4' THEN 'Finals'
                   END
               WHEN ps.series_end = ps.season_end THEN 'Finals'
               ELSE 'playoffs'
           END AS round
    FROM nba.games g
    LEFT JOIN season_names h ON h.season = g.season AND h.team_id = g.home_team_id
    LEFT JOIN season_names a ON a.season = g.season AND a.team_id = g.away_team_id
    LEFT JOIN playoff_series ps USING (game_id)
),
games AS (
    SELECT 'game' AS kind, game_id AS id,
           concat(strftime(game_date, '%Y-%m-%d'), ' ', coalesce(away_abbr, '?'), ' @ ',
                  coalesce(home_abbr, '?'), ', ',
                  CASE
                      WHEN round IS NOT NULL THEN round || ' game ' || series_game
                      WHEN season_type = 'regular' THEN 'regular season'
                      WHEN season_type = 'nba-cup' THEN 'NBA Cup final'
                      ELSE season_type
                  END) AS label,
           NULL::VARCHAR AS key,
           list_distinct(list_filter([
               trim(regexp_replace(lower(strip_accents(home_name)), '[^a-z0-9]+', ' ', 'g')),
               trim(regexp_replace(lower(strip_accents(away_name)), '[^a-z0-9]+', ' ', 'g')),
               (season - 1) || ' ' || lpad(((season) % 100)::VARCHAR, 2, '0'),
               season_type,
               CASE WHEN round IS NOT NULL THEN 'playoffs' END
           ], lambda x: x IS NOT NULL)) AS aliases,
           season AS season_min, season AS season_max,
           concat(coalesce(away_name, '?'), ' ', coalesce(away_pts::VARCHAR, '?'), ', ',
                  coalesce(home_name, '?'), ' ', coalesce(home_pts::VARCHAR, '?')) AS context
    FROM game_rows
)
SELECT * FROM players
UNION ALL
SELECT * FROM teams
UNION ALL
SELECT kind, id, label,
       trim(regexp_replace(regexp_replace(lower(strip_accents(label)),
            '[''.]', '', 'g'), '[^a-z0-9]+', ' ', 'g')) AS key,
       aliases, season_min, season_max, context
FROM games
