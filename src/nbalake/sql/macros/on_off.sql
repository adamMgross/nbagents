-- Team points for and against per 100 possessions with the player on and off the floor, per team he played for, over the games he played. On/off is the on row's net_rating minus the off row's. Possession points run low before 2017-18.
-- example: from on_off(201939, 2016)
CREATE OR REPLACE TEMP MACRO on_off(player_id, season, season_type := 'regular') AS TABLE
WITH args AS (
    SELECT player_id AS player_id, season AS season, season_type AS season_type
),
p AS (
    SELECT
        ps.game_id, ps.offense_team_id, ps.defense_team_id, ps.points,
        list_contains([ps.off_player_1, ps.off_player_2, ps.off_player_3, ps.off_player_4,
                       ps.off_player_5], a.player_id) AS on_offense,
        list_contains([ps.def_player_1, ps.def_player_2, ps.def_player_3, ps.def_player_4,
                       ps.def_player_5], a.player_id) AS on_defense
    FROM args a
    JOIN nba.possessions ps ON ps.season = a.season
    JOIN nba.games g ON g.game_id = ps.game_id
    WHERE ps.count_as_possession
      AND (a.season_type IS NULL OR g.season_type = a.season_type)
),
played AS (
    SELECT DISTINCT p.game_id, p.offense_team_id AS team_id FROM p WHERE p.on_offense
    UNION
    SELECT DISTINCT p.game_id, p.defense_team_id FROM p WHERE p.on_defense
),
sides AS (
    SELECT pl.team_id, p.on_offense AS on_court, true AS offense, p.points
    FROM p JOIN played pl ON pl.game_id = p.game_id AND pl.team_id = p.offense_team_id
    UNION ALL
    SELECT pl.team_id, p.on_defense, false, p.points
    FROM p JOIN played pl ON pl.game_id = p.game_id AND pl.team_id = p.defense_team_id
)
SELECT
    s.team_id, s.on_court,
    count(*) FILTER (WHERE s.offense) AS off_possessions,
    count(*) FILTER (WHERE NOT s.offense) AS def_possessions,
    per_100(sum(s.points) FILTER (WHERE s.offense), count(*) FILTER (WHERE s.offense))
        AS off_rating,
    per_100(sum(s.points) FILTER (WHERE NOT s.offense), count(*) FILTER (WHERE NOT s.offense))
        AS def_rating,
    off_rating - def_rating AS net_rating
FROM sides s
GROUP BY s.team_id, s.on_court
ORDER BY s.team_id, s.on_court DESC;
