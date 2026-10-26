SELECT
    season, game_id, official_id,
    trim(first_name || ' ' || last_name) AS name,
    first_name, last_name,
    nullif(trim(jersey_num), '') AS jersey_num
FROM sdv.nba_stats_officials
