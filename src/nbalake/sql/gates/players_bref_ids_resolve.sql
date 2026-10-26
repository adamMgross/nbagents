SELECT DISTINCT t.player_id
FROM bref.player_totals t
ANTI JOIN nba.player_xref x ON x.source = 'bref' AND x.source_id = t.player_id
