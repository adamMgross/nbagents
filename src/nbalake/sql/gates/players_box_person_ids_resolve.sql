SELECT DISTINCT b.person_id
FROM sdv.nba_stats_player_boxscores b
ANTI JOIN nba.player_xref x ON x.source = 'nba' AND x.source_id = b.person_id::VARCHAR
WHERE trim(concat(b.first_name, b.family_name)) <> ''
