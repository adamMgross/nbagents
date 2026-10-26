SELECT DISTINCT code
FROM (SELECT home AS code FROM odds.lines UNION SELECT away FROM odds.lines) c
ANTI JOIN nba.odds_teams t USING (code)
