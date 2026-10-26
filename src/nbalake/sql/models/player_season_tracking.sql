WITH keys AS (
    SELECT season, season_type, player_id, player_name, team_id, team_abbreviation, gp, w, l, min
    FROM sdv.leaguedash_player_tracking_drives WHERE per_mode = 'Totals' AND season >= 2014
    UNION ALL
    SELECT season, season_type, player_id, player_name, team_id, team_abbreviation, gp, w, l, min
    FROM sdv.leaguedash_player_tracking_catchshoot WHERE per_mode = 'Totals' AND season >= 2014
    UNION ALL
    SELECT season, season_type, player_id, player_name, team_id, team_abbreviation, gp, w, l, min
    FROM sdv.leaguedash_player_tracking_pullupshot WHERE per_mode = 'Totals' AND season >= 2014
    UNION ALL
    SELECT season, season_type, player_id, player_name, team_id, team_abbreviation, gp, w, l, min
    FROM sdv.leaguedash_player_tracking_elbowtouch WHERE per_mode = 'Totals' AND season >= 2014
    UNION ALL
    SELECT season, season_type, player_id, player_name, team_id, team_abbreviation, gp, w, l, min
    FROM sdv.leaguedash_player_tracking_posttouch WHERE per_mode = 'Totals' AND season >= 2014
    UNION ALL
    SELECT season, season_type, player_id, player_name, team_id, team_abbreviation, gp, w, l, min
    FROM sdv.leaguedash_player_tracking_painttouch WHERE per_mode = 'Totals' AND season >= 2014
    UNION ALL
    SELECT season, season_type, player_id, player_name, team_id, team_abbreviation, gp, w, l, min
    FROM sdv.leaguedash_player_tracking_passing WHERE per_mode = 'Totals' AND season >= 2014
    UNION ALL
    SELECT season, season_type, player_id, player_name, team_id, team_abbreviation, gp, w, l, min
    FROM sdv.leaguedash_player_tracking_possessions WHERE per_mode = 'Totals' AND season >= 2014
    UNION ALL
    SELECT season, season_type, player_id, player_name, team_id, team_abbreviation, gp, w, l, min
    FROM sdv.leaguedash_player_tracking_speeddistance WHERE per_mode = 'Totals' AND season >= 2014
    UNION ALL
    SELECT season, season_type, player_id, player_name, team_id, team_abbreviation, gp, w, l, min
    FROM sdv.leaguedash_player_tracking_rebounding WHERE per_mode = 'Totals' AND season >= 2014
    UNION ALL
    SELECT season, season_type, player_id, player_name, team_id, team_abbreviation, gp, w, l, min
    FROM sdv.leaguedash_player_tracking_defense WHERE per_mode = 'Totals' AND season >= 2014
    UNION ALL
    SELECT season, season_type, player_id, player_name, team_id, team_abbreviation, gp, w, l, min
    FROM sdv.leaguedash_player_tracking_efficiency WHERE per_mode = 'Totals' AND season >= 2014
),
k AS (
    SELECT
        season, season_type, player_id,
        arg_max(player_name, gp) AS player_name,
        arg_max(team_id, gp) AS last_team_id,
        arg_max(team_abbreviation, gp) AS last_team,
        max(gp) AS gp,
        max(w) AS w,
        max(l) AS l,
        max(min) AS min
    FROM keys
    GROUP BY season, season_type, player_id
)
SELECT
    k.season,
    CASE k.season_type WHEN 'Regular Season' THEN 'regular' WHEN 'Playoffs' THEN 'playoffs'
        ELSE lower(k.season_type) END AS season_type,
    k.player_id, k.player_name, k.last_team_id, k.last_team, k.gp, k.w, k.l, k.min,
    t0.drives,
    t0.drive_fgm,
    t0.drive_fga,
    t0.drive_fg_pct,
    t0.drive_ftm,
    t0.drive_fta,
    t0.drive_ft_pct,
    t0.drive_pts,
    t0.drive_pts_pct,
    t0.drive_passes,
    t0.drive_passes_pct,
    t0.drive_ast,
    t0.drive_ast_pct,
    t0.drive_tov,
    t0.drive_tov_pct,
    t0.drive_pf,
    t0.drive_pf_pct,
    t1.catch_shoot_fgm,
    t1.catch_shoot_fga,
    t1.catch_shoot_pts,
    t1.catch_shoot_fg_pct,
    t1.catch_shoot_fg3_m,
    t1.catch_shoot_fg3_a,
    t1.catch_shoot_fg3_pct,
    t1.catch_shoot_efg_pct,
    t2.pull_up_fgm,
    t2.pull_up_fga,
    t2.pull_up_pts,
    t2.pull_up_fg_pct,
    t2.pull_up_fg3_m,
    t2.pull_up_fg3_a,
    t2.pull_up_fg3_pct,
    t2.pull_up_efg_pct,
    t3.touches,
    t3.elbow_touches,
    t3.elbow_touch_fgm,
    t3.elbow_touch_fga,
    t3.elbow_touch_fg_pct,
    t3.elbow_touch_ftm,
    t3.elbow_touch_fta,
    t3.elbow_touch_ft_pct,
    t3.elbow_touch_pts,
    t3.elbow_touch_pts_pct,
    t3.elbow_touch_passes,
    t3.elbow_touch_passes_pct,
    t3.elbow_touch_ast,
    t3.elbow_touch_ast_pct,
    t3.elbow_touch_tov,
    t3.elbow_touch_tov_pct,
    t3.elbow_touch_fouls,
    t3.elbow_touch_fouls_pct,
    t4.post_touches,
    t4.post_touch_fgm,
    t4.post_touch_fga,
    t4.post_touch_fg_pct,
    t4.post_touch_ftm,
    t4.post_touch_fta,
    t4.post_touch_ft_pct,
    t4.post_touch_pts,
    t4.post_touch_pts_pct,
    t4.post_touch_passes,
    t4.post_touch_passes_pct,
    t4.post_touch_ast,
    t4.post_touch_ast_pct,
    t4.post_touch_tov,
    t4.post_touch_tov_pct,
    t4.post_touch_fouls,
    t4.post_touch_fouls_pct,
    t5.paint_touches,
    t5.paint_touch_fgm,
    t5.paint_touch_fga,
    t5.paint_touch_fg_pct,
    t5.paint_touch_ftm,
    t5.paint_touch_fta,
    t5.paint_touch_ft_pct,
    t5.paint_touch_pts,
    t5.paint_touch_pts_pct,
    t5.paint_touch_passes,
    t5.paint_touch_passes_pct,
    t5.paint_touch_ast,
    t5.paint_touch_ast_pct,
    t5.paint_touch_tov,
    t5.paint_touch_tov_pct,
    t5.paint_touch_fouls,
    t5.paint_touch_fouls_pct,
    t6.passes_made,
    t6.passes_received,
    t6.ast,
    t6.ft_ast,
    t6.secondary_ast,
    t6.potential_ast,
    t6.ast_pts_created,
    t6.ast_adj,
    t6.ast_to_pass_pct,
    t6.ast_to_pass_pct_adj,
    t7.points,
    t7.front_ct_touches,
    t7.time_of_poss,
    t7.avg_sec_per_touch,
    t7.avg_drib_per_touch,
    t7.pts_per_touch,
    t7.pts_per_elbow_touch,
    t7.pts_per_post_touch,
    t7.pts_per_paint_touch,
    t8.dist_feet,
    t8.dist_miles,
    t8.dist_miles_off,
    t8.dist_miles_def,
    t8.avg_speed,
    t8.avg_speed_off,
    t8.avg_speed_def,
    t9.oreb,
    t9.oreb_contest,
    t9.oreb_uncontest,
    t9.oreb_contest_pct,
    t9.oreb_chances,
    t9.oreb_chance_pct,
    t9.oreb_chance_defer,
    t9.oreb_chance_pct_adj,
    t9.avg_oreb_dist,
    t9.dreb,
    t9.dreb_contest,
    t9.dreb_uncontest,
    t9.dreb_contest_pct,
    t9.dreb_chances,
    t9.dreb_chance_pct,
    t9.dreb_chance_defer,
    t9.dreb_chance_pct_adj,
    t9.avg_dreb_dist,
    t9.reb,
    t9.reb_contest,
    t9.reb_uncontest,
    t9.reb_contest_pct,
    t9.reb_chances,
    t9.reb_chance_pct,
    t9.reb_chance_defer,
    t9.reb_chance_pct_adj,
    t9.avg_reb_dist,
    t10.stl,
    t10.blk,
    t10.def_rim_fgm,
    t10.def_rim_fga,
    t10.def_rim_fg_pct,
    t11.eff_fg_pct
FROM k
LEFT JOIN sdv.leaguedash_player_tracking_drives t0
    ON t0.season = k.season AND t0.season_type = k.season_type AND t0.player_id = k.player_id
    AND t0.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_tracking_catchshoot t1
    ON t1.season = k.season AND t1.season_type = k.season_type AND t1.player_id = k.player_id
    AND t1.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_tracking_pullupshot t2
    ON t2.season = k.season AND t2.season_type = k.season_type AND t2.player_id = k.player_id
    AND t2.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_tracking_elbowtouch t3
    ON t3.season = k.season AND t3.season_type = k.season_type AND t3.player_id = k.player_id
    AND t3.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_tracking_posttouch t4
    ON t4.season = k.season AND t4.season_type = k.season_type AND t4.player_id = k.player_id
    AND t4.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_tracking_painttouch t5
    ON t5.season = k.season AND t5.season_type = k.season_type AND t5.player_id = k.player_id
    AND t5.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_tracking_passing t6
    ON t6.season = k.season AND t6.season_type = k.season_type AND t6.player_id = k.player_id
    AND t6.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_tracking_possessions t7
    ON t7.season = k.season AND t7.season_type = k.season_type AND t7.player_id = k.player_id
    AND t7.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_tracking_speeddistance t8
    ON t8.season = k.season AND t8.season_type = k.season_type AND t8.player_id = k.player_id
    AND t8.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_tracking_rebounding t9
    ON t9.season = k.season AND t9.season_type = k.season_type AND t9.player_id = k.player_id
    AND t9.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_tracking_defense t10
    ON t10.season = k.season AND t10.season_type = k.season_type AND t10.player_id = k.player_id
    AND t10.per_mode = 'Totals'
LEFT JOIN sdv.leaguedash_player_tracking_efficiency t11
    ON t11.season = k.season AND t11.season_type = k.season_type AND t11.player_id = k.player_id
    AND t11.per_mode = 'Totals'
