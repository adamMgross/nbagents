WITH calls AS (
    SELECT
        row_number() OVER (ORDER BY gid, page, file, time2 DESC, call_type, committing, disadvantaged) AS call_id,
        gid AS game_id,
        TRY_CAST(replace(period, 'Q', '') AS INTEGER) AS period,
        time_min * 60 + time_sec AS seconds_remaining,
        call_type, call, type,
        nullif(decision, '') AS decision,
        nullif(committing, '') AS committing_name,
        nullif(committing_team, '') AS committing_team,
        nullif(disadvantaged, '') AS disadvantaged_name,
        nullif(disadvantaged_team, '') AS disadvantaged_team,
        nullif(comments, '') AS comment,
        OFFICIAL_ID_1 AS official_1_id, OFFICIAL_ID_2 AS official_2_id,
        OFFICIAL_ID_3 AS official_3_id, OFFICIAL_ID_4 AS official_4_id,
        OFFICIAL_1 AS official_1, OFFICIAL_2 AS official_2, OFFICIAL_3 AS official_3, OFFICIAL_4 AS official_4,
        home_score, away_score, national_tv, file AS report_file
    FROM l2m.calls
),
keyed AS (
    SELECT
        b.game_id, b.team_id, b.player_id, p.name, p.last_name,
        trim(regexp_replace(regexp_replace(lower(strip_accents(p.name)), '[^a-z ]', '', 'g'), '\s+(jr|sr|ii|iii|iv)$', '')) AS key
    FROM nba.player_box b
    JOIN nba.players p USING (player_id)
    WHERE b.game_id IN (SELECT game_id FROM calls)
),
named AS (
    SELECT c.call_id, v.side, c.game_id, t.team_id, v.name,
           trim(regexp_replace(regexp_replace(lower(strip_accents(v.name)), '[^a-z ]', '', 'g'), '\s+(jr|sr|ii|iii|iv)$', '')) AS key
    FROM calls c
    JOIN nba.games g USING (game_id)
    CROSS JOIN LATERAL (VALUES ('committing', c.committing_name, c.committing_team), ('disadvantaged', c.disadvantaged_name, c.disadvantaged_team)) v(side, name, team)
    LEFT JOIN nba.team_seasons t ON t.season = g.season AND t.abbreviation = v.team
    WHERE v.name IS NOT NULL
),
by_name AS (
    SELECT n.call_id, n.side, any_value(k.player_id) AS player_id, 'box_name' AS method
    FROM named n
    JOIN keyed k ON k.game_id = n.game_id AND k.key = n.key
    GROUP BY ALL
    HAVING count(DISTINCT k.player_id) = 1
),
by_last AS (
    SELECT n.call_id, n.side, any_value(k.player_id) AS player_id, 'box_last_name' AS method
    FROM named n
    JOIN keyed k
      ON k.game_id = n.game_id AND (n.team_id IS NULL OR k.team_id = n.team_id)
     AND (split_part(k.key, ' ', -1) = split_part(n.key, ' ', -1)
          OR (n.key NOT LIKE '% %' AND split_part(k.key, ' ', 1) = n.key))
    WHERE (n.call_id, n.side) NOT IN (SELECT (call_id, side) FROM by_name)
    GROUP BY ALL
    HAVING count(DISTINCT k.player_id) = 1
),
resolved AS (
    SELECT * FROM by_name UNION ALL SELECT * FROM by_last
),
teams AS (
    SELECT call_id, side, team_id FROM named
),
nicknames AS (
    SELECT DISTINCT simpleName AS name FROM l2m.teams
)
SELECT
    c.call_id,
    c.game_id,
    g.season,
    g.season_type,
    g.game_date,
    c.period,
    c.seconds_remaining,
    c.call_type, c.call, c.type, c.decision,
    c.committing_name,
    c.committing_name IN (SELECT name FROM nicknames) AS committing_is_team,
    rc.player_id AS committing_player_id,
    rc.method AS committing_resolution,
    tc.team_id AS committing_team_id,
    c.disadvantaged_name,
    rd.player_id AS disadvantaged_player_id,
    rd.method AS disadvantaged_resolution,
    td.team_id AS disadvantaged_team_id,
    c.comment,
    c.official_1_id, c.official_2_id, c.official_3_id, c.official_4_id,
    c.official_1, c.official_2, c.official_3, c.official_4,
    c.home_score, c.away_score, c.national_tv, c.report_file
FROM calls c
LEFT JOIN nba.games g USING (game_id)
LEFT JOIN resolved rc ON rc.call_id = c.call_id AND rc.side = 'committing'
LEFT JOIN resolved rd ON rd.call_id = c.call_id AND rd.side = 'disadvantaged'
LEFT JOIN teams tc ON tc.call_id = c.call_id AND tc.side = 'committing'
LEFT JOIN teams td ON td.call_id = c.call_id AND td.side = 'disadvantaged'
