SELECT
    t.season::INTEGER AS season,
    t.lg,
    x.player_id,
    f.team_id,
    f.team_id IS NULL AS multi_team,
    t.player_id AS bref_id,
    t.team AS bref_team,
    t.* EXCLUDE (_unit, _sha256, _fetched_at, season, lg, player_id, team),
    a.* EXCLUDE (_unit, _sha256, _fetched_at, season, lg, player, player_id, age, team, pos, g, gs, mp),
    c.* EXCLUDE (_unit, _sha256, _fetched_at, season, lg, player, player_id, age, team, pos, g, gs, mp,
                 fg_percent, x3p_percent, x2p_percent, e_fg_percent, ft_percent),
    s.* EXCLUDE (_unit, _sha256, _fetched_at, season, lg, player, player_id, age, team, pos, g, gs, mp, fg_percent),
    p.* EXCLUDE (_unit, _sha256, _fetched_at, season, lg, player, player_id, age, team, pos, g, gs, mp),
    i.experience
FROM bref.player_totals t
JOIN nba.player_xref x ON x.source = 'bref' AND x.source_id = t.player_id
LEFT JOIN nba.franchises f ON f.code = t.team
LEFT JOIN bref.player_advanced a
  ON a.season = t.season AND a.lg = t.lg AND a.player_id = t.player_id AND a.team = t.team
LEFT JOIN bref.player_per_100 c
  ON c.season = t.season AND c.lg = t.lg AND c.player_id = t.player_id AND c.team = t.team
LEFT JOIN bref.player_shooting s
  ON s.season = t.season AND s.lg = t.lg AND s.player_id = t.player_id AND s.team = t.team
LEFT JOIN bref.player_play_by_play p
  ON p.season = t.season AND p.lg = t.lg AND p.player_id = t.player_id AND p.team = t.team
LEFT JOIN bref.player_season_info i
  ON i.season = t.season AND i.lg = t.lg AND i.player_id = t.player_id AND i.team = t.team
