SELECT
    t.season::INTEGER AS season,
    t.lg,
    f.team_id,
    t.* EXCLUDE (_unit, _sha256, _fetched_at, season, lg),
    c.* EXCLUDE (_unit, _sha256, _fetched_at, season, lg, team, abbreviation, playoffs, g, mp,
                 fg_percent, x3p_percent, x2p_percent, ft_percent),
    o.* EXCLUDE (_unit, _sha256, _fetched_at, season, lg, team, abbreviation, playoffs, g, mp),
    q.* EXCLUDE (_unit, _sha256, _fetched_at, season, lg, team, abbreviation, playoffs, g, mp,
                 opp_fg_percent, opp_x3p_percent, opp_x2p_percent, opp_ft_percent)
FROM bref.team_totals t
JOIN nba.franchises f ON f.code = t.abbreviation
LEFT JOIN bref.team_per_100 c ON c.season = t.season AND c.lg = t.lg AND c.team = t.team
LEFT JOIN bref.opponent_totals o ON o.season = t.season AND o.lg = t.lg AND o.team = t.team
LEFT JOIN bref.opponent_per_100 q ON q.season = t.season AND q.lg = t.lg AND q.team = t.team
