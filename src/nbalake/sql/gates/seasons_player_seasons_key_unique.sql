SELECT season, lg, bref_id, bref_team, count(*) AS n FROM nba.player_seasons GROUP BY ALL HAVING count(*) > 1
