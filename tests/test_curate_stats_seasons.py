from __future__ import annotations

from collections.abc import Iterator

import duckdb
import pytest

from nbalake.curate import check
from nbalake.lake import Root
from tests.curated import build_models, empty_lake, gate, insert, rows, sources

MODELS = (
    "arenas",
    "franchises",
    "team_seasons",
    "teams",
    "games",
    "team_elo",
    "team_games",
    "espn_bref_links",
    "player_xref",
    "players",
    "recorded_from",
    "player_seasons",
    "player_season_dash",
    "team_season_dash",
    "player_season_tracking",
    "player_season_hustle",
    "team_season_hustle",
    "player_season_play_types",
    "matchups_game",
    "matchups_season",
    "player_impact",
    "player_season_closest_defender",
    "team_season_closest_defender",
)
HARRIS, LAC, PHI = 202699, 1610612746, 1610612755
PEOPLE = ("franchises", "espn_bref_links", "player_xref", "players")
GAMES = ("franchises", "team_seasons", "games")


@pytest.fixture
def con(root: Root) -> Iterator[duckdb.DuckDBPyConnection]:
    con = empty_lake(root, sources(*MODELS, gate_prefix="seasons_"))
    yield con
    con.close()


def dash(table: str, **values: object) -> dict:
    return {
        "season": 2019,
        "season_type": "Regular Season",
        "per_mode": "Totals",
        "player_id": HARRIS,
        "player_name": "Tobias Harris",
        "team_id": PHI,
        "team_abbreviation": "PHI",
        "gp": 82,
        **values,
    }


def test_player_season_dash_merges_measures_into_one_row_on_the_last_team(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.leaguedash_player_stats_base",
        [
            dash("base", pts=1644, fgm=609, pts_rank=20, team_count=2),
            dash("base", season_type="Playoffs", pts=211, gp=12),
        ],
    )
    insert(
        con,
        "sdv.leaguedash_player_stats_advanced",
        [dash("advanced", usg_pct=0.234, fgm=1, net_rating_rank=40)],
    )
    build_models(con, "player_season_dash")

    assert rows(
        con,
        "SELECT season_type, last_team_id, last_team, gp, pts, fgm, usg_pct, team_count "
        "FROM nba.player_season_dash ORDER BY season_type",
    ) == [
        ("playoffs", PHI, "PHI", 12, 211, None, None, None),
        ("regular", PHI, "PHI", 82, 1644, 609, 0.234, 2),
    ]
    cols = {c for (c,) in rows(con, "SELECT column_name FROM (DESCRIBE nba.player_season_dash)")}
    assert not {c for c in cols if c.endswith("_rank")} | ({"team_id", "per_mode"} & cols)


def test_player_season_tracking_starts_in_2014_and_merges_the_tracking_tables(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.leaguedash_player_tracking_pullupshot",
        [
            dash("pull", season=2013, pull_up_fga=0),
            dash("pull", season=2019, pull_up_fga=120, pull_up_pts=150),
        ],
    )
    insert(con, "sdv.leaguedash_player_tracking_drives", [dash("drives", drives=300)])
    insert(
        con,
        "sdv.leaguedash_player_tracking_efficiency",
        [dash("eff", pull_up_pts=999, eff_fg_pct=0.5)],
    )
    build_models(con, "player_season_tracking")

    assert rows(
        con,
        "SELECT season, season_type, drives, pull_up_fga, pull_up_pts, eff_fg_pct "
        "FROM nba.player_season_tracking",
    ) == [(2019, "regular", 300, 120, 150, 0.5)]
    assert check(con, gate("seasons_player_season_tracking_starts_in_2014")).violations == 0


def test_season_dash_gates_flag_unknown_players_odd_season_types_and_bref_disagreement(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(con, "sdv.leaguedash_player_stats_base", [dash("base", pts=1644, season_type="Pre")])
    insert(
        con,
        "sdv.leaguedash_team_stats_base",
        [{"season": 2019, "season_type": "Regular Season", "per_mode": "Totals", "team_id": PHI}],
    )
    build_models(con, *PEOPLE, "player_season_dash", "team_season_dash", "player_season_tracking")

    assert check(con, gate("seasons_player_season_dash_key_unique")).violations == 0
    assert check(con, gate("seasons_team_season_dash_key_unique")).violations == 0
    assert check(
        con, gate("seasons_player_season_dash_players_resolve_over_99_percent")
    ).sample == [{"unresolved": 1, "player_seasons": 1}]
    assert check(con, gate("seasons_dash_season_types_are_regular_or_playoffs")).sample == [
        {"table_name": "player_season_dash", "season_type": "pre", "n": 1}
    ]


def test_the_bref_points_gate_flags_a_season_more_than_two_points_off(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "bref.player_career_info",
        [{"player_id": "harrito02", "player": "Tobias Harris", "from": 2012, "to": 2026}],
    )
    totals = {"season": 2019, "lg": "NBA", "player_id": "harrito02", "g": 82}
    insert(
        con,
        "bref.player_totals",
        [
            {**totals, "team": "2TM", "pts": 1644},
            {**totals, "team": "LAC", "pts": 1152},
            {**totals, "team": "PHI", "pts": 492},
        ],
    )
    build_models(con, *PEOPLE, "recorded_from", "player_seasons", "player_season_dash")
    ((pid,),) = rows(con, "SELECT DISTINCT player_id FROM nba.player_seasons")
    name = "seasons_player_season_dash_points_off_bref_by_over_2_under_0_1_percent"
    insert(con, "sdv.leaguedash_player_stats_base", [dash("base", player_id=pid, pts=1645)])
    build_models(con, *PEOPLE, "recorded_from", "player_seasons", "player_season_dash")
    assert check(con, gate(name)).violations == 0

    con.execute("DELETE FROM sdv.leaguedash_player_stats_base")
    insert(con, "sdv.leaguedash_player_stats_base", [dash("base", player_id=pid, pts=1650)])
    build_models(con, *PEOPLE, "recorded_from", "player_seasons", "player_season_dash")

    assert check(con, gate(name)).sample == [{"off": 1, "player_seasons": 1}]


def synergy(side: str, play_type: str, team: int, poss: float, **values: object) -> dict:
    return {
        "season": 2019,
        "season_type": "regular-season",
        "per_mode": "totals",
        "side": side,
        "type_grouping": side.title(),
        "play_type": play_type,
        "player_id": HARRIS,
        "player_name": "Tobias Harris",
        "team_id": team,
        "team_abbreviation": {LAC: "LAC", PHI: "PHI"}[team],
        "poss": poss,
        **values,
    }


def test_play_types_keep_totals_one_row_per_team_and_name_the_side(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_synergy",
        [
            synergy("offensive", "Isolation", LAC, 120.0, ppp=0.95, percentile=0.6),
            synergy("offensive", "Isolation", PHI, 60.0, ppp=1.01, percentile=0.7),
            synergy("defensive", "Postup", PHI, 40.0),
            {**synergy("offensive", "Isolation", LAC, 4.0), "per_mode": "pergame"},
        ],
    )
    build_models(con, "player_season_play_types")

    assert rows(
        con,
        "SELECT season_type, side, play_type, team_id, team, poss, ppp "
        "FROM nba.player_season_play_types ORDER BY side, team_id",
    ) == [
        ("regular", "defense", "Postup", PHI, "PHI", 40.0, None),
        ("regular", "offense", "Isolation", LAC, "LAC", 120.0, 0.95),
        ("regular", "offense", "Isolation", PHI, "PHI", 60.0, 1.01),
    ]
    assert check(con, gate("seasons_player_season_play_types_key_unique")).violations == 0


def test_hustle_keeps_totals_on_the_last_team(con: duckdb.DuckDBPyConnection) -> None:
    hustle = {"season": 2019, "season_type": "regular-season", "player_id": HARRIS}
    insert(
        con,
        "sdv.hustle_player",
        [
            {
                **hustle,
                "per_mode": "totals",
                "team_id": PHI,
                "team_abbreviation": "PHI",
                "g": 82,
                "deflections": 120.0,
            },
            {**hustle, "per_mode": "pergame", "team_id": PHI, "g": 82, "deflections": 1.5},
        ],
    )
    insert(
        con,
        "sdv.hustle_team",
        [
            {
                "season": 2019,
                "season_type": "playoffs",
                "per_mode": "totals",
                "team_id": PHI,
                "team_name": "76ers",
                "screen_assists": 300.0,
            }
        ],
    )
    build_models(con, "player_season_hustle", "team_season_hustle")

    assert rows(
        con, "SELECT season_type, last_team_id, gp, deflections FROM nba.player_season_hustle"
    ) == [("regular", PHI, 82, 120.0)]
    assert rows(con, "SELECT season_type, team_id, screen_assists FROM nba.team_season_hustle") == [
        ("playoffs", PHI, 300.0)
    ]


def test_play_type_gates_flag_implausible_possessions_in_finished_seasons_and_unknown_teams(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            {
                "game_id": "0021800001",
                "season": 2019,
                "season_type": "regular-season",
                "game_date": "2018-10-16",
                "home_team_id": PHI,
                "away_team_id": LAC,
                "home_pts": 100,
                "away_pts": 90,
            },
            {
                "game_id": "0021900001",
                "season": 2020,
                "season_type": "regular-season",
                "game_date": "2019-10-22",
                "home_team_id": PHI,
                "away_team_id": LAC,
                "home_pts": 100,
                "away_pts": 90,
            },
        ],
    )
    insert(
        con,
        "sdv.nba_stats_synergy",
        [
            synergy("offensive", "Isolation", PHI, 100.0),
            synergy("offensive", "Isolation", PHI, 10.0, season=2020),
        ],
    )
    build_models(con, "arenas", *GAMES, "team_elo", "team_games", "player_season_play_types")
    per_game = gate("seasons_play_types_offense_possessions_per_team_game_between_75_and_130")
    assert check(con, per_game).violations == 0

    insert(con, "sdv.nba_stats_synergy", [synergy("offensive", "Cut", PHI, 100.0)])
    build_models(con, "arenas", *GAMES, "team_elo", "team_games", "player_season_play_types")

    assert check(con, per_game).sample == [{"season": 2019, "team_id": PHI, "per_game": 200.0}]


GAME = "0021800001"


def schedule(con: duckdb.DuckDBPyConnection) -> None:
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            {
                "game_id": GAME,
                "season": 2019,
                "season_type": "regular-season",
                "game_date": "2018-10-16",
                "home_team_id": PHI,
                "away_team_id": LAC,
                "home_pts": 100,
                "away_pts": 90,
            }
        ],
    )


def matchup(defender: int, poss: float, **values: object) -> dict:
    return {
        "game_id": GAME,
        "season": 2019,
        "season_type_id": "2",
        "side": "home",
        "off_team_id": PHI,
        "def_team_id": LAC,
        "off_person_id": HARRIS,
        "def_person_id": defender,
        "matchup_minutes": "1:30",
        "matchup_minutes_sort": 90.0,
        "partial_possessions": poss,
        "off_first_name": "Tobias",
        **values,
    }


def test_matchups_game_names_players_and_seconds_and_takes_the_game_season_type(
    con: duckdb.DuckDBPyConnection,
) -> None:
    schedule(con)
    insert(con, "sdv.nba_stats_game_matchups", [matchup(1, 3.5, player_points=4)])
    insert(
        con,
        "sdv.season_matchups",
        [
            {
                "season": 2019,
                "season_type": "regular-season",
                "per_mode": per_mode,
                "off_player_id": HARRIS,
                "def_player_id": 1,
                "gp": 3,
                "partial_poss": poss,
            }
            for per_mode, poss in (("totals", 30.0), ("pergame", 10.0))
        ],
    )
    build_models(con, *GAMES, "matchups_game", "matchups_season")

    assert rows(
        con,
        "SELECT season_type, off_player_id, def_player_id, matchup_seconds, partial_possessions, "
        "player_points FROM nba.matchups_game",
    ) == [("regular", HARRIS, 1, 90.0, 3.5, 4)]
    assert rows(con, "SELECT season_type, gp, partial_poss FROM nba.matchups_season") == [
        ("regular", 3, 30.0)
    ]
    cols = {c for (c,) in rows(con, "SELECT column_name FROM (DESCRIBE nba.matchups_game)")}
    assert "off_first_name" not in cols and "matchup_minutes" not in cols


def test_the_shuf_matchups_gate_flags_disagreeing_partial_possessions(
    con: duckdb.DuckDBPyConnection,
) -> None:
    schedule(con)
    insert(con, "sdv.nba_stats_game_matchups", [matchup(1, 3.5), matchup(2, 1.0)])
    shuf = {"game_id": int(GAME), "person_id": HARRIS, "season": 2019}
    insert(
        con,
        "shuf.matchups",
        [
            {**shuf, "matchups_person_id": 1, "partial_possessions": 3.4},
            {**shuf, "matchups_person_id": 2, "partial_possessions": 1.2},
        ],
    )
    build_models(con, *GAMES, "matchups_game")
    name = "seasons_matchups_game_agree_with_shuf_under_0_5_percent"
    assert check(con, gate(name)).violations == 0

    con.execute("UPDATE shuf.matchups SET partial_possessions = 9.0 WHERE matchups_person_id = 2")

    assert check(con, gate(name)).sample == [{"off": 1, "matchups": 2}]


def test_player_impact_names_the_primary_team_and_lists_every_team(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_player_impact",
        [
            {
                "season": 2019,
                "season_type": "Regular Season",
                "player_id": 202710,
                "team_id": PHI,
                "team_abbreviation": "PHI",
                "team_name": "76ers",
                "teams": "PHI,MIN",
                "gp": 65,
                "rapm": 2.1,
                "darko_projected_rating": 3.0,
            }
        ],
    )
    build_models(con, "player_impact")

    assert rows(
        con,
        "SELECT season_type, primary_team_id, primary_team, teams, rapm, darko_projected_rating "
        "FROM nba.player_impact",
    ) == [("regular", PHI, "PHI", ["PHI", "MIN"], 2.1, 3.0)]
    assert check(con, gate("seasons_player_impact_key_unique")).violations == 0


def team_names(con: duckdb.DuckDBPyConnection) -> None:
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            {
                "game_id": "0021800001",
                "season": 2019,
                "season_type": "regular-season",
                "game_date": "2018-10-16",
                "home_team_id": PHI,
                "home_team_abbreviation": "PHI",
                "away_team_id": LAC,
                "away_team_abbreviation": "LAC",
                "home_pts": 100,
                "away_pts": 90,
            }
        ],
    )
    insert(
        con,
        "bref.team_summaries",
        [{"season": 2019, "lg": "NBA", "abbreviation": "PHI", "team": "Philadelphia 76ers"}],
    )


def by_defender(band: str, fga: int, **values: object) -> dict:
    return {
        "season": 2019,
        "season_type": "regular",
        "defender_distance": band,
        "GP": 82,
        "G": 70,
        "FGM": fga // 2,
        "FGA": fga,
        "2FGM": fga // 4,
        "2FGA": fga // 2,
        "3PM": fga // 4,
        "3PA": fga // 2,
        **values,
    }


def harris(band: str, fga: int, team: str) -> dict:
    return by_defender(band, fga, PLAYER_ID=HARRIS, PLAYER="Tobias Harris", TEAM=team, AGE=26.0)


def test_closest_defender_keeps_counts_by_band_and_maps_team_names_and_abbreviations(
    con: duckdb.DuckDBPyConnection,
) -> None:
    team_names(con)
    insert(
        con,
        "gab.player_shots_by_defender",
        [harris("wide_open", 100, "Philadelphia 76ers"), harris("very_tight", 40, "PHI")],
    )
    insert(con, "gab.team_shots_by_defender", [by_defender("open", 2000, TEAM="PHI")])
    insert(
        con,
        "gab.opponent_shots_by_defender",
        [by_defender("open", 1900, TEAM="Philadelphia 76ers")],
    )
    build_models(con, *GAMES, "player_season_closest_defender", "team_season_closest_defender")

    assert rows(
        con,
        "SELECT player_id, last_team_id, defender_distance, defender_ft_min, gp, "
        "games_with_shot, fga, fg3a FROM nba.player_season_closest_defender "
        "ORDER BY defender_ft_min",
    ) == [
        (HARRIS, PHI, "very_tight", 0, 82, 70, 40, 20),
        (HARRIS, PHI, "wide_open", 6, 82, 70, 100, 50),
    ]
    assert rows(
        con,
        "SELECT team_id, side, defender_distance, fga FROM nba.team_season_closest_defender "
        "ORDER BY side",
    ) == [(PHI, "defense", "open", 1900), (PHI, "offense", "open", 2000)]
    assert check(con, gate("seasons_closest_defender_teams_resolve")).violations == 0


def test_closest_defender_gates_flag_unknown_teams_and_bands_that_miss_season_attempts(
    con: duckdb.DuckDBPyConnection,
) -> None:
    team_names(con)
    insert(
        con,
        "gab.player_shots_by_defender",
        [harris("wide_open", 300, "PHI"), harris("very_tight", 100, "PHI")],
    )
    insert(con, "gab.team_shots_by_defender", [by_defender("open", 2000, TEAM="XYZ")])
    insert(con, "sdv.leaguedash_player_stats_base", [dash("base", fga=400.0, fgm=180.0)])
    build_models(
        con,
        *PEOPLE,
        *GAMES,
        "player_season_dash",
        "player_season_closest_defender",
        "team_season_closest_defender",
    )
    attempts = gate("seasons_player_season_closest_defender_fga_within_10_percent_of_dash")
    assert check(con, attempts).violations == 0
    assert check(con, gate("seasons_closest_defender_teams_resolve")).sample == [
        {"season": 2019, "season_type": "regular", "side": "offense", "team": "XYZ"}
    ]

    insert(con, "sdv.leaguedash_player_stats_base", [dash("base", fga=500.0, season=2020)])
    insert(
        con,
        "gab.player_shots_by_defender",
        [{**harris("open", 400, "PHI"), "season": 2020}],
    )
    build_models(con, "player_season_dash", "player_season_closest_defender")

    assert check(con, attempts).sample == [
        {"season": 2020, "season_type": "regular", "player_id": HARRIS, "bands": 400, "fga": 500.0}
    ]
