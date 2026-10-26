SELECT s.id AS espn_game_id, s.date
FROM sdv.espn_nba_schedule_master s
ANTI JOIN nba.games g ON g.espn_game_id = s.id
WHERE s.status_type_completed
  AND s.season_type IN (2, 3, 5) AND s.type_abbreviation <> 'ALLSTAR'
  AND s.home_score + s.away_score > 0
  AND CAST(timezone('America/New_York', CAST(s.date AS TIMESTAMPTZ)) AS DATE)
      > (SELECT max(game_date) FROM nba.games WHERE source = 'nba')
