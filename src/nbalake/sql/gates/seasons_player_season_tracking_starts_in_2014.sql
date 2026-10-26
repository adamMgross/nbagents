SELECT season, count(*) AS n
FROM nba.player_season_tracking
WHERE season < 2014
GROUP BY season
