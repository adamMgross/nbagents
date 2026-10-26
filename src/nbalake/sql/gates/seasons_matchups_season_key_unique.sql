SELECT season, season_type, off_player_id, def_player_id, count(*) AS n
FROM nba.matchups_season
GROUP BY ALL
HAVING count(*) > 1
