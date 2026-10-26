SELECT season, season_type, side, play_type, player_id, team_id, count(*) AS n
FROM nba.player_season_play_types
GROUP BY ALL
HAVING count(*) > 1
