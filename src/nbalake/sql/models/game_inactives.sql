SELECT
    season, game_id, team_id, player_id,
    trim(first_name || ' ' || last_name) AS name,
    nullif(trim(jersey_num), '') AS jersey_num
FROM sdv.nba_stats_game_rosters
