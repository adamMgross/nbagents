SELECT 'player_season_dash' AS table_name, season_type, count(*) AS n
FROM nba.player_season_dash WHERE season_type NOT IN ('regular', 'playoffs') GROUP BY ALL
UNION ALL
SELECT 'team_season_dash', season_type, count(*)
FROM nba.team_season_dash WHERE season_type NOT IN ('regular', 'playoffs') GROUP BY ALL
UNION ALL
SELECT 'player_season_tracking', season_type, count(*)
FROM nba.player_season_tracking WHERE season_type NOT IN ('regular', 'playoffs') GROUP BY ALL
