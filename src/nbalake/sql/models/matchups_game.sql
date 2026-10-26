SELECT
    m.season, m.game_id, g.season_type,
    m.off_team_id, m.def_team_id, m.side,
    m.off_person_id AS off_player_id, m.def_person_id AS def_player_id,
    m.matchup_minutes_sort AS matchup_seconds,
    m.* EXCLUDE (
        season, game_id, off_team_id, def_team_id, side, off_person_id, def_person_id,
        matchup_minutes, matchup_minutes_sort, season_type_id,
        off_team_city, off_team_name, off_team_tricode, off_team_slug,
        off_first_name, off_family_name, off_name_i, off_player_slug, off_position,
        off_comment, off_jersey_num,
        def_first_name, def_family_name, def_name_i, def_player_slug, def_jersey_num,
        _unit, _sha256, _fetched_at
    )
FROM sdv.nba_stats_game_matchups m
LEFT JOIN nba.games g USING (game_id)
