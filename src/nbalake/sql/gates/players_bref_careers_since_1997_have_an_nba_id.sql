SELECT source_id, name, first_season, last_season
FROM nba.player_xref
WHERE source = 'bref' AND method = 'minted' AND last_season >= 1997
