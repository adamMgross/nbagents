SELECT player_id
FROM nba.players
WHERE coalesce(trim(name), '') = ''
