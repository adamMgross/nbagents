WITH keys AS (
    SELECT season, season_type, team_id, team_name, gp, w, l, w_pct, min
    FROM sdv.leaguedash_team_stats_base WHERE per_mode = 'Totals'
    UNION ALL
    SELECT season, season_type, team_id, team_name, gp, w, l, w_pct, min
    FROM sdv.leaguedash_team_stats_advanced WHERE per_mode = 'Totals'
    UNION ALL
    SELECT season, season_type, team_id, team_name, gp, w, l, w_pct, min
    FROM sdv.leaguedash_team_stats_misc WHERE per_mode = 'Totals'
    UNION ALL
    SELECT season, season_type, team_id, team_name, gp, w, l, w_pct, min
    FROM sdv.leaguedash_team_stats_scoring WHERE per_mode = 'Totals'
    UNION ALL
    SELECT season, season_type, team_id, team_name, gp, w, l, w_pct, min
    FROM sdv.leaguedash_team_stats_defense WHERE per_mode = 'Totals'
    UNION ALL
    SELECT season, season_type, team_id, team_name, gp, w, l, w_pct, min
    FROM sdv.leaguedash_team_stats_fourfactors WHERE per_mode = 'Totals'
    UNION ALL
    SELECT season, season_type, team_id, team_name, gp, w, l, w_pct, min
    FROM sdv.leaguedash_team_stats_opponent WHERE per_mode = 'Totals'
),
k AS (
    SELECT
        season, season_type, team_id,
        arg_max(team_name, gp) AS team_name,
        max(gp) AS gp,
        max(w) AS w,
        max(l) AS l,
        arg_max(w_pct, gp) AS w_pct,
        max(min) AS min
    FROM keys
    GROUP BY season, season_type, team_id
)
SELECT
    k.season,
    CASE k.season_type WHEN 'Regular Season' THEN 'regular' WHEN 'Playoffs' THEN 'playoffs'
        ELSE lower(k.season_type) END AS season_type,
    k.team_id, k.team_name, k.gp, k.w, k.l, k.w_pct, k.min,
    t0.fgm,
    t0.fga,
    t0.fg_pct,
    t0.fg3_m,
    t0.fg3_a,
    t0.fg3_pct,
    t0.ftm,
    t0.fta,
    t0.ft_pct,
    t0.oreb,
    t0.dreb,
    t0.reb,
    t0.ast,
    t0.tov,
    t0.stl,
    t0.blk,
    t0.blka,
    t0.pf,
    t0.pfd,
    t0.pts,
    t0.plus_minus,
    t1.e_off_rating,
    t1.off_rating,
    t1.e_def_rating,
    t1.def_rating,
    t1.e_net_rating,
    t1.net_rating,
    t1.ast_pct,
    t1.ast_to,
    t1.ast_ratio,
    t1.oreb_pct,
    t1.dreb_pct,
    t1.reb_pct,
    t1.tm_tov_pct,
    t1.efg_pct,
    t1.ts_pct,
    t1.e_pace,
    t1.pace,
    t1.pace_per40,
    t1.poss,
    t1.pie,
    t2.pts_off_tov,
    t2.pts_2_nd_chance,
    t2.pts_fb,
    t2.pts_paint,
    t2.opp_pts_off_tov,
    t2.opp_pts_2_nd_chance,
    t2.opp_pts_fb,
    t2.opp_pts_paint,
    t3.pct_fga_2_pt,
    t3.pct_fga_3_pt,
    t3.pct_pts_2_pt,
    t3.pct_pts_2_pt_mr,
    t3.pct_pts_3_pt,
    t3.pct_pts_fb,
    t3.pct_pts_ft,
    t3.pct_pts_off_tov,
    t3.pct_pts_paint,
    t3.pct_ast_2_pm,
    t3.pct_uast_2_pm,
    t3.pct_ast_3_pm,
    t3.pct_uast_3_pm,
    t3.pct_ast_fgm,
    t3.pct_uast_fgm,
    t5.fta_rate,
    t5.opp_efg_pct,
    t5.opp_fta_rate,
    t5.opp_tov_pct,
    t5.opp_oreb_pct,
    t6.opp_fgm,
    t6.opp_fga,
    t6.opp_fg_pct,
    t6.opp_fg3_m,
    t6.opp_fg3_a,
    t6.opp_fg3_pct,
    t6.opp_ftm,
    t6.opp_fta,
    t6.opp_ft_pct,
    t6.opp_oreb,
    t6.opp_dreb,
    t6.opp_reb,
    t6.opp_ast,
    t6.opp_tov,
    t6.opp_stl,
    t6.opp_blk,
    t6.opp_blka,
    t6.opp_pf,
    t6.opp_pfd,
    t6.opp_pts
FROM k
LEFT JOIN sdv.leaguedash_team_stats_base t0
    ON t0.season = k.season AND t0.season_type = k.season_type AND t0.team_id = k.team_id
    AND t0.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_team_stats_advanced t1
    ON t1.season = k.season AND t1.season_type = k.season_type AND t1.team_id = k.team_id
    AND t1.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_team_stats_misc t2
    ON t2.season = k.season AND t2.season_type = k.season_type AND t2.team_id = k.team_id
    AND t2.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_team_stats_scoring t3
    ON t3.season = k.season AND t3.season_type = k.season_type AND t3.team_id = k.team_id
    AND t3.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_team_stats_defense t4
    ON t4.season = k.season AND t4.season_type = k.season_type AND t4.team_id = k.team_id
    AND t4.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_team_stats_fourfactors t5
    ON t5.season = k.season AND t5.season_type = k.season_type AND t5.team_id = k.team_id
    AND t5.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_team_stats_opponent t6
    ON t6.season = k.season AND t6.season_type = k.season_type AND t6.team_id = k.team_id
    AND t6.per_mode = 'Totals'
