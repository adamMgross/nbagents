WITH keys AS (
    SELECT season, season_type, player_id, player_name, nickname, team_id, team_abbreviation, age, gp, w, l, w_pct, min
    FROM sdv.leaguedash_player_stats_base WHERE per_mode = 'Totals'
    UNION ALL
    SELECT season, season_type, player_id, player_name, nickname, team_id, team_abbreviation, age, gp, w, l, w_pct, min
    FROM sdv.leaguedash_player_stats_advanced WHERE per_mode = 'Totals'
    UNION ALL
    SELECT season, season_type, player_id, player_name, nickname, team_id, team_abbreviation, age, gp, w, l, w_pct, min
    FROM sdv.leaguedash_player_stats_misc WHERE per_mode = 'Totals'
    UNION ALL
    SELECT season, season_type, player_id, player_name, nickname, team_id, team_abbreviation, age, gp, w, l, w_pct, min
    FROM sdv.leaguedash_player_stats_scoring WHERE per_mode = 'Totals'
    UNION ALL
    SELECT season, season_type, player_id, player_name, nickname, team_id, team_abbreviation, age, gp, w, l, w_pct, min
    FROM sdv.leaguedash_player_stats_usage WHERE per_mode = 'Totals'
    UNION ALL
    SELECT season, season_type, player_id, player_name, nickname, team_id, team_abbreviation, age, gp, w, l, w_pct, min
    FROM sdv.leaguedash_player_stats_defense WHERE per_mode = 'Totals'
),
k AS (
    SELECT
        season, season_type, player_id,
        arg_max(player_name, gp) AS player_name,
        arg_max(nickname, gp) AS nickname,
        arg_max(team_id, gp) AS last_team_id,
        arg_max(team_abbreviation, gp) AS last_team,
        arg_max(age, gp) AS age,
        max(gp) AS gp,
        max(w) AS w,
        max(l) AS l,
        arg_max(w_pct, gp) AS w_pct,
        max(min) AS min
    FROM keys
    GROUP BY season, season_type, player_id
)
SELECT
    k.season,
    CASE k.season_type WHEN 'Regular Season' THEN 'regular' WHEN 'Playoffs' THEN 'playoffs'
        ELSE lower(k.season_type) END AS season_type,
    k.player_id, k.player_name, k.nickname, k.last_team_id, k.last_team, k.age, k.gp, k.w, k.l, k.w_pct, k.min,
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
    t0.nba_fantasy_pts,
    t0.dd2,
    t0.td3,
    t0.wnba_fantasy_pts,
    t0.team_count,
    t0.fp_high_score,
    t1.e_off_rating,
    t1.off_rating,
    t1.sp_work_off_rating,
    t1.e_def_rating,
    t1.def_rating,
    t1.sp_work_def_rating,
    t1.e_net_rating,
    t1.net_rating,
    t1.sp_work_net_rating,
    t1.ast_pct,
    t1.ast_to,
    t1.ast_ratio,
    t1.oreb_pct,
    t1.dreb_pct,
    t1.reb_pct,
    t1.tm_tov_pct,
    t1.e_tov_pct,
    t1.efg_pct,
    t1.ts_pct,
    t1.usg_pct,
    t1.e_usg_pct,
    t1.e_pace,
    t1.pace,
    t1.pace_per40,
    t1.sp_work_pace,
    t1.pie,
    t1.poss,
    t1.fgm_pg,
    t1.fga_pg,
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
    t4.pct_fgm,
    t4.pct_fga,
    t4.pct_fg3_m,
    t4.pct_fg3_a,
    t4.pct_ftm,
    t4.pct_fta,
    t4.pct_oreb,
    t4.pct_dreb,
    t4.pct_reb,
    t4.pct_ast,
    t4.pct_tov,
    t4.pct_stl,
    t4.pct_blk,
    t4.pct_blka,
    t4.pct_pf,
    t4.pct_pfd,
    t4.pct_pts,
    t5.def_ws,
    t5.def_ws_raw
FROM k
LEFT JOIN sdv.leaguedash_player_stats_base t0
    ON t0.season = k.season AND t0.season_type = k.season_type AND t0.player_id = k.player_id
    AND t0.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_stats_advanced t1
    ON t1.season = k.season AND t1.season_type = k.season_type AND t1.player_id = k.player_id
    AND t1.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_stats_misc t2
    ON t2.season = k.season AND t2.season_type = k.season_type AND t2.player_id = k.player_id
    AND t2.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_stats_scoring t3
    ON t3.season = k.season AND t3.season_type = k.season_type AND t3.player_id = k.player_id
    AND t3.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_stats_usage t4
    ON t4.season = k.season AND t4.season_type = k.season_type AND t4.player_id = k.player_id
    AND t4.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_stats_defense t5
    ON t5.season = k.season AND t5.season_type = k.season_type AND t5.player_id = k.player_id
    AND t5.per_mode = 'Totals'
