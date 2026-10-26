from __future__ import annotations

from collections.abc import Iterator

import duckdb
import pytest

from nbalake.curate import check
from nbalake.lake import Root
from tests.curated import build_models, empty_lake, gate, insert, rows, sources

MODELS = (
    "franchises",
    "team_seasons",
    "games",
    "espn_bref_links",
    "player_xref",
    "players",
    "team_box",
    "player_box",
    "game_inactives",
    "box_reconciliation",
)
BOS, LAL = 1610612738, 1610612747
GAME = "0021700001"


def team_row(game_id: str, team_id: int, points: int, minutes: str = "240:00") -> dict:
    return {
        "game_id": game_id,
        "team_id": team_id,
        "points": points,
        "minutes": minutes,
        "season": 2018,
    }


def player_row(
    game_id: str,
    team_id: int,
    person_id: int,
    minutes: str,
    points: int,
    position: str = "",
    comment: str = "",
) -> dict:
    return {
        "game_id": game_id,
        "team_id": team_id,
        "person_id": person_id,
        "first_name": f"P{person_id}",
        "family_name": "Test",
        "minutes": minutes,
        "points": points,
        "position": position,
        "comment": comment,
        "season": 2018,
    }


@pytest.fixture
def con(root: Root) -> Iterator[duckdb.DuckDBPyConnection]:
    con = empty_lake(root, sources(*MODELS, gate_prefix="boxes_"))
    yield con
    con.close()


def nba_game(con: duckdb.DuckDBPyConnection, season: int = 2018, game_id: str = GAME) -> None:
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            {
                "game_id": game_id,
                "season": season,
                "season_type": "regular-season",
                "game_date": f"{season - 1}-11-01",
                "home_team_id": BOS,
                "away_team_id": LAL,
                "home_pts": 100,
                "away_pts": 90,
            }
        ],
    )


def test_nba_boxes_convert_minutes_mark_dnps_and_know_starters_only_from_2018(
    con: duckdb.DuckDBPyConnection,
) -> None:
    nba_game(con)
    nba_game(con, season=2017, game_id="0021600001")
    insert(
        con,
        "sdv.nba_stats_team_boxscores",
        [team_row(GAME, BOS, 100), team_row(GAME, LAL, 90), team_row(GAME, 0, 0)],
    )
    insert(
        con,
        "sdv.nba_stats_player_boxscores",
        [
            player_row(GAME, BOS, 1, "34:12", 60, position="G"),
            player_row(GAME, BOS, 2, "10:05", 40),
            player_row(GAME, BOS, 3, "", 0, comment="DNP - Coach's Decision"),
            player_row("0021600001", BOS, 1, "30:00", 50, position="G"),
        ],
    )

    build_models(con, *MODELS)

    assert rows(
        con,
        "SELECT game_id, player_id, seconds, played, started, dnp_reason "
        "FROM nba.player_box ORDER BY game_id, player_id",
    ) == [
        ("0021600001", 1, 1800, True, None, None),
        (GAME, 1, 2052, True, True, None),
        (GAME, 2, 605, True, False, None),
        (GAME, 3, None, False, False, "DNP - Coach's Decision"),
    ]
    assert rows(
        con,
        "SELECT team_id, opponent_team_id, is_home, seconds, pts "
        "FROM nba.team_box ORDER BY team_id",
    ) == [
        (BOS, LAL, True, 14400, 100),
        (LAL, BOS, False, 14400, 90),
    ]


def test_pre_1997_boxes_come_from_espn_with_xref_player_ids(con: duckdb.DuckDBPyConnection) -> None:
    insert(
        con,
        "sdv.nba_team_crosswalk",
        [
            {"season": 1995, "espn_team_id": e, "nba_team_id": str(t)}
            for t, e in ((BOS, 2), (LAL, 13))
        ],
    )
    insert(
        con,
        "fte.elo",
        [
            {
                "game_id": "199501050BOS",
                "date_game": "1995-01-05",
                "year_id": 1995,
                "lg_id": "NBA",
                "_iscopy": 0,
                "is_playoffs": 0,
                "team_id": "BOS",
                "opp_id": "LAL",
                "pts": 101,
                "opp_pts": 99,
                "game_location": "H",
            }
        ],
    )
    insert(
        con,
        "sdv.espn_nba_schedule_master",
        [
            {
                "id": 150105002,
                "date": "1995-01-06T00:30Z",
                "season": 1995,
                "season_type": 2,
                "home_id": 2,
                "away_id": 13,
                "home_score": 101,
                "away_score": 99,
            }
        ],
    )
    insert(
        con,
        "sdv.espn_nba_team_boxscores",
        [
            {
                "game_id": 150105002,
                "team_id": 2,
                "team_score": 101,
                "field_goals_made": 40,
                "total_turnovers": 15,
            },
            {
                "game_id": 150105002,
                "team_id": 13,
                "team_score": 99,
                "field_goals_made": 38,
                "total_turnovers": 12,
            },
        ],
    )
    insert(
        con,
        "bref.player_career_info",
        [{"player_id": "brownde01", "player": "Dee Brown", "from": 1991, "to": 2002}],
    )
    insert(
        con,
        "sdv.espn_nba_player_boxscores",
        [
            {
                "game_id": 150105002,
                "team_id": 2,
                "athlete_id": 7,
                "athlete_display_name": "Dee Brown",
                "season": 1995,
                "minutes": 30.0,
                "points": 101,
                "starter": True,
            },
            {
                "game_id": 150105002,
                "team_id": 13,
                "athlete_id": 8,
                "athlete_display_name": "Unknown Guy",
                "season": 1995,
                "minutes": 0.0,
                "points": 99,
                "did_not_play": False,
            },
        ],
    )

    build_models(con, *MODELS)

    brown = rows(
        con,
        "SELECT player_id FROM nba.player_xref WHERE source = 'bref' AND source_id = 'brownde01'",
    )[0][0]
    assert rows(
        con, "SELECT team_id, pts, fgm, tov, source FROM nba.team_box ORDER BY team_id"
    ) == [
        (BOS, 101, 40, 15, "espn"),
        (LAL, 99, 38, 12, "espn"),
    ]
    assert rows(
        con,
        "SELECT team_id, player_id, seconds, played, started FROM nba.player_box ORDER BY team_id",
    ) == [
        (BOS, brown, 1800, True, True),
        (LAL, None, 0, False, False),
    ]
    assert rows(con, "SELECT team_id, unresolved_players FROM nba.box_reconciliation") == [(LAL, 1)]


def test_boxes_gates_pass_on_consistent_boxes_and_flag_each_violation(
    con: duckdb.DuckDBPyConnection,
) -> None:
    nba_game(con)
    insert(con, "sdv.nba_stats_team_boxscores", [team_row(GAME, BOS, 100), team_row(GAME, LAL, 90)])
    insert(
        con,
        "sdv.nba_stats_player_boxscores",
        [
            player_row(GAME, BOS, 1, "48:00", 100, position="G"),
            player_row(GAME, LAL, 2, "48:00", 90, position="G"),
        ],
    )
    build_models(con, *MODELS)
    names = (
        "boxes_team_box_two_rows_per_game",
        "boxes_team_box_points_agree_with_games",
        "boxes_team_box_teams_have_a_season",
        "boxes_nba_player_points_sum_to_team_under_0_01_percent",
        "boxes_espn_player_points_sum_to_team_under_1_percent",
        "boxes_nba_box_players_exist",
        "boxes_player_seconds_within_game_length",
    )
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)
    assert rows(con, "SELECT count(*) FROM nba.box_reconciliation") == [(0,)]

    con.execute(
        "UPDATE sdv.nba_stats_player_boxscores SET minutes = '49:01', points = 97 "
        "WHERE person_id = 1"
    )
    build_models(con, *MODELS)

    assert check(con, gate("boxes_player_seconds_within_game_length")).sample[0]["seconds"] == 2941
    assert check(con, gate("boxes_nba_player_points_sum_to_team_under_0_01_percent")).sample == [
        {"differing": 1, "sides": 2}
    ]
    assert rows(con, "SELECT side, team_box_pts, player_sum_pts FROM nba.box_reconciliation") == [
        ("home", 100, 97)
    ]


def inactive(player_id: int, game_id: str = GAME, team_id: int = BOS) -> dict:
    return {
        "game_id": game_id,
        "team_id": team_id,
        "player_id": player_id,
        "first_name": f"P{player_id}",
        "last_name": "Test",
        "jersey_num": " 7",
        "season": 2018,
    }


def test_game_inactives_list_who_sat_out_and_their_gates_flag_each_violation(
    con: duckdb.DuckDBPyConnection,
) -> None:
    nba_game(con)
    insert(con, "sdv.nba_stats_player_boxscores", [player_row(GAME, BOS, 1, "34:12", 60)])
    insert(con, "sdv.nba_stats_game_rosters", [inactive(1)])
    build_models(con, *MODELS)
    names = (
        "boxes_game_inactives_key_unique",
        "boxes_game_inactives_games_exist",
        "boxes_game_inactives_players_resolve_over_99_percent",
    )
    assert rows(
        con, "SELECT game_id, team_id, player_id, name, jersey_num FROM nba.game_inactives"
    ) == [(GAME, BOS, 1, "P1 Test", "7")]
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)

    insert(
        con,
        "sdv.nba_stats_game_rosters",
        [inactive(1), inactive(99), inactive(1, game_id="0029999999")],
    )
    build_models(con, *MODELS)

    assert check(con, gate(names[0])).sample == [
        {"game_id": GAME, "team_id": BOS, "player_id": 1, "n": 2}
    ]
    assert check(con, gate(names[1])).sample == [{"game_id": "0029999999"}]
    assert check(con, gate(names[2])).sample == [{"unresolved": 1, "inactives": 4}]


def test_espn_game_rosters_set_started_before_2018_only_where_espn_lists_five_starters(
    con: duckdb.DuckDBPyConnection,
) -> None:
    game = "0020900001"
    nba_game(con, season=2010, game_id=game)
    insert(con, "sdv.nba_schedule_crosswalk", [{"nba_game_id": game, "espn_game_id": "290001"}])
    players = {BOS: range(1, 7), LAL: range(7, 12)}
    insert(
        con,
        "sdv.nba_stats_player_boxscores",
        [
            {**player_row(game, team, pid, "20:00", 2), "season": 2010}
            for team, ids in players.items()
            for pid in ids
        ],
    )
    insert(
        con,
        "sdv.nba_player_crosswalk",
        [
            {
                "season": 2010,
                "espn_athlete_id": str(100 + pid),
                "nba_player_id": str(pid),
                "espn_full_name": f"P{pid} Test",
            }
            for ids in players.values()
            for pid in ids
        ],
    )
    espn_team = {BOS: 2, LAL: 13}
    insert(
        con,
        "sdv.espn_nba_game_rosters",
        [
            {
                "season": 2010,
                "game_id": "290001",
                "team_id": espn_team[team],
                "athlete_id": 100 + pid,
                "starter": i < (5 if team == BOS else 4),
            }
            for team, ids in players.items()
            for i, pid in enumerate(ids)
        ],
    )
    build_models(con, *MODELS)

    assert rows(
        con,
        "SELECT team_id, list(started ORDER BY player_id), list(DISTINCT started_source) "
        "FROM nba.player_box GROUP BY 1 ORDER BY 1",
    ) == [
        (BOS, [True, True, True, True, True, False], ["espn"]),
        (LAL, [None, None, None, None, None], [None]),
    ]
    five = gate("boxes_five_starters_per_team_game_over_99_5_percent")
    assert check(con, five).violations == 0

    insert(
        con,
        "sdv.espn_nba_game_rosters",
        [{"season": 2010, "game_id": "290001", "team_id": 13, "athlete_id": 999, "starter": True}],
    )
    build_models(con, *MODELS)

    assert check(con, five).sample == [{"off": 1, "team_games": 2}]


def test_without_a_team_box_the_player_sum_is_checked_against_the_schedule_score(
    con: duckdb.DuckDBPyConnection,
) -> None:
    nba_game(con)
    insert(
        con,
        "sdv.nba_stats_player_boxscores",
        [player_row(GAME, BOS, 1, "40:00", 100), player_row(GAME, LAL, 2, "40:00", 89)],
    )
    build_models(con, *MODELS)

    assert rows(
        con,
        "SELECT team_id, team_box_missing, schedule_pts, player_sum_pts, player_sum_differs "
        "FROM nba.box_reconciliation ORDER BY team_id",
    ) == [(BOS, True, 100, 100, False), (LAL, True, 90, 89, True)]


def test_a_side_with_no_team_box_and_no_players_is_missing_not_a_player_sum_mismatch(
    con: duckdb.DuckDBPyConnection,
) -> None:
    nba_game(con)
    build_models(con, *MODELS)

    assert rows(
        con,
        "SELECT team_box_missing, player_sum_pts, player_sum_differs FROM nba.box_reconciliation",
    ) == [(True, None, False), (True, None, False)]


def test_a_game_only_espn_has_published_carries_espn_boxes_under_its_minted_id(
    con: duckdb.DuckDBPyConnection,
) -> None:
    nba_game(con)
    insert(
        con,
        "sdv.nba_team_crosswalk",
        [
            {"season": 2018, "espn_team_id": e, "nba_team_id": str(t)}
            for t, e in ((BOS, 2), (LAL, 13))
        ],
    )
    insert(
        con,
        "sdv.espn_nba_schedule_master",
        [
            {
                "id": 401000002,
                "date": "2017-11-06T00:30Z",
                "season": 2018,
                "season_type": 2,
                "type_abbreviation": "STD",
                "home_id": 13,
                "away_id": 2,
                "home_score": 99,
                "away_score": 101,
                "status_type_completed": True,
            }
        ],
    )
    insert(
        con,
        "sdv.espn_nba_team_boxscores",
        [
            {"game_id": 401000002, "team_id": 13, "team_score": 99},
            {"game_id": 401000002, "team_id": 2, "team_score": 101},
        ],
    )
    insert(
        con,
        "sdv.espn_nba_player_boxscores",
        [
            {
                "game_id": 401000002,
                "team_id": 2,
                "athlete_id": 7,
                "season": 2018,
                "minutes": 30.0,
                "points": 101,
                "starter": True,
            }
        ],
    )

    build_models(con, *MODELS)

    assert rows(
        con,
        "SELECT game_id, team_id, is_home, pts, source FROM nba.team_box WHERE source = 'espn'"
        " ORDER BY team_id",
    ) == [("espn401000002", BOS, False, 101, "espn"), ("espn401000002", LAL, True, 99, "espn")]
    assert rows(
        con, "SELECT game_id, team_id, seconds, source FROM nba.player_box WHERE source = 'espn'"
    ) == [("espn401000002", BOS, 1800, "espn")]


def test_a_box_era_game_with_no_espn_id_is_listed_as_missing_a_box(
    con: duckdb.DuckDBPyConnection,
) -> None:
    def fte_game(game_id: str, day: str, location: str) -> dict:
        return {
            "game_id": game_id,
            "date_game": day,
            "year_id": 1995,
            "lg_id": "NBA",
            "_iscopy": 0,
            "is_playoffs": 0,
            "team_id": "BOS",
            "opp_id": "LAL",
            "pts": 101,
            "opp_pts": 99,
            "game_location": location,
        }

    insert(
        con,
        "sdv.nba_team_crosswalk",
        [
            {"season": 1995, "espn_team_id": e, "nba_team_id": str(t)}
            for t, e in ((BOS, 2), (LAL, 13))
        ],
    )
    insert(
        con,
        "fte.elo",
        [fte_game("199501050BOS", "1995-01-05", "H"), fte_game("199501070BOS", "1995-01-07", "N")],
    )
    insert(
        con,
        "sdv.espn_nba_schedule_master",
        [
            {
                "id": 150105002,
                "date": "1995-01-06T00:30Z",
                "season": 1995,
                "season_type": 2,
                "home_id": 2,
                "away_id": 13,
                "home_score": 101,
                "away_score": 99,
            }
        ],
    )
    insert(
        con,
        "sdv.espn_nba_team_boxscores",
        [
            {"game_id": 150105002, "team_id": 2, "team_score": 101},
            {"game_id": 150105002, "team_id": 13, "team_score": 99},
        ],
    )

    build_models(con, *MODELS)

    assert rows(
        con,
        "SELECT DISTINCT game_id FROM nba.box_reconciliation WHERE team_box_missing",
    ) == [("199501070BOS",)]


def test_a_nameless_nba_box_row_is_a_coach_and_makes_no_player_box_row(
    con: duckdb.DuckDBPyConnection,
) -> None:
    nba_game(con)
    nameless = player_row(GAME, BOS, 1345, "", 0)
    nameless["first_name"] = ""
    nameless["family_name"] = ""
    insert(
        con,
        "sdv.nba_stats_player_boxscores",
        [player_row(GAME, BOS, 1, "34:12", 60), nameless],
    )

    build_models(con, *MODELS)

    assert rows(con, "SELECT player_id FROM nba.player_box") == [(1,)]
