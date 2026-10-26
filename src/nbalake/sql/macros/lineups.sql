-- Five-man units for one team, or every team when team_id is NULL, with possessions and ratings per 100. A unit needs min_possessions on offense and again on defense.
-- example: from lineups(1610612744, 2016, 300) order by net_rating desc
CREATE OR REPLACE TEMP MACRO lineups(team_id, season, min_possessions := 100, season_type := 'regular') AS TABLE
WITH args AS (
    SELECT team_id AS team_id, season AS season, min_possessions AS min_possessions,
           season_type AS season_type
),
p AS (
    SELECT ps.offense_team_id, ps.defense_team_id, ps.points,
        list_sort([ps.off_player_1, ps.off_player_2, ps.off_player_3, ps.off_player_4,
                   ps.off_player_5]) AS off5,
        list_sort([ps.def_player_1, ps.def_player_2, ps.def_player_3, ps.def_player_4,
                   ps.def_player_5]) AS def5
    FROM args a
    JOIN nba.possessions ps ON ps.season = a.season
    JOIN nba.games g ON g.game_id = ps.game_id
    WHERE ps.count_as_possession
      AND (a.season_type IS NULL OR g.season_type = a.season_type)
      AND (a.team_id IS NULL OR a.team_id IN (ps.offense_team_id, ps.defense_team_id))
),
units AS (
    SELECT p.offense_team_id AS unit_team_id, p.off5 AS unit, true AS offense, p.points FROM p
    UNION ALL
    SELECT p.defense_team_id, p.def5, false, p.points FROM p
),
rated AS (
    SELECT u.unit_team_id, u.unit,
        count(*) FILTER (WHERE u.offense) AS off_possessions,
        count(*) FILTER (WHERE NOT u.offense) AS def_possessions,
        per_100(sum(u.points) FILTER (WHERE u.offense), count(*) FILTER (WHERE u.offense))
            AS off_rating,
        per_100(sum(u.points) FILTER (WHERE NOT u.offense), count(*) FILTER (WHERE NOT u.offense))
            AS def_rating
    FROM units u, args a
    WHERE a.team_id IS NULL OR u.unit_team_id = a.team_id
    GROUP BY u.unit_team_id, u.unit, a.min_possessions
    HAVING least(count(*) FILTER (WHERE u.offense), count(*) FILTER (WHERE NOT u.offense))
        >= a.min_possessions
),
members AS (
    SELECT r.unit_team_id, r.unit, unnest(r.unit) AS member FROM rated r
),
named AS (
    SELECT m.unit_team_id, m.unit,
        string_agg(coalesce(pl.name, m.member::VARCHAR), ', '
                   ORDER BY coalesce(pl.name, m.member::VARCHAR)) AS players
    FROM members m LEFT JOIN nba.players pl ON pl.player_id = m.member
    GROUP BY m.unit_team_id, m.unit
)
SELECT r.unit_team_id AS team_id, ts.abbreviation AS team, n.players, r.unit AS player_ids,
    r.off_possessions, r.def_possessions, r.off_rating, r.def_rating,
    r.off_rating - r.def_rating AS net_rating
FROM rated r
JOIN named n ON n.unit_team_id = r.unit_team_id AND n.unit = r.unit
CROSS JOIN args a
LEFT JOIN nba.team_seasons ts ON ts.team_id = r.unit_team_id AND ts.season = a.season
ORDER BY r.off_possessions DESC;
