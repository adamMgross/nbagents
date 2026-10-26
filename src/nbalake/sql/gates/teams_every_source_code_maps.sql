SELECT DISTINCT 'bref' AS source, s.abbreviation AS code
FROM bref.team_summaries s ANTI JOIN nba.franchises f ON f.code = s.abbreviation
WHERE s.team <> 'League Average'
UNION ALL
SELECT DISTINCT 'fte', e.team_id
FROM fte.elo e ANTI JOIN nba.franchises f ON f.code = e.team_id
