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
    "player_box",
    "game_officials",
    "officials",
    "l2m_calls",
    "l2m_games",
)
MIA, DEN = 1610612748, 1610612743
GAME = "0021400925"


def call(
    committing: str,
    team: str = "MIA",
    decision: str = "CNC",
    period: str = "Q4",
    minute: int = 1,
    second: float = 30.0,
    **extra: object,
) -> dict:
    return {
        "gid": GAME,
        "page": 1,
        "file": "L2M-MIA-DEN.pdf",
        "time2": minute * 60 + second,
        "period": period,
        "time_min": minute,
        "time_sec": second,
        "call_type": "Foul: Shooting",
        "committing": committing,
        "committing_team": team,
        "disadvantaged": "",
        "decision": decision,
        **extra,
    }


def box(person_id: int, first: str, family: str, team: int) -> dict:
    return {
        "game_id": GAME,
        "team_id": team,
        "person_id": person_id,
        "first_name": first,
        "family_name": family,
        "season": 2015,
        "minutes": "30:00",
    }


@pytest.fixture
def con(root: Root) -> Iterator[duckdb.DuckDBPyConnection]:
    con = empty_lake(root, sources(*MODELS, gate_prefix="officiating_"))
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            {
                "game_id": GAME,
                "season": 2015,
                "season_type": "regular-season",
                "game_date": "2015-03-10",
                "home_team_id": DEN,
                "home_team_abbreviation": "DEN",
                "away_team_id": MIA,
                "away_team_abbreviation": "MIA",
                "home_pts": 100,
                "away_pts": 98,
            }
        ],
    )
    insert(
        con,
        "sdv.nba_stats_player_boxscores",
        [
            box(201196, "Henry", "Walker", MIA),
            box(2403, "Nene", "Hilario", DEN),
            box(202711, "Bojan", "Bogdanović", DEN),
            box(203109, "Hassan", "Whiteside", MIA),
        ],
    )
    insert(con, "l2m.teams", [{"teamId": MIA, "abbreviation": "MIA", "simpleName": "Heat"}])
    yield con
    con.close()


def test_calls_resolve_players_by_name_last_name_and_single_name_and_flag_team_calls(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "l2m.calls",
        [
            call("Henry Walker"),
            call("Bojan Bogdanovic", team="DEN", minute=1, second=20.0),
            call("H. Whiteside", minute=1, second=10.0),
            call("Nene", team="DEN", minute=0, second=50.0),
            call("Heat", minute=0, second=40.0, call_type="Turnover: 5 Second Inbound"),
        ],
    )

    build_models(con, *MODELS)

    assert rows(
        con,
        "SELECT committing_name, committing_player_id, committing_resolution, committing_is_team, "
        "committing_team_id FROM nba.l2m_calls ORDER BY seconds_remaining DESC",
    ) == [
        ("Henry Walker", 201196, "box_name", False, MIA),
        ("Bojan Bogdanovic", 202711, "box_name", False, DEN),
        ("H. Whiteside", 203109, "box_last_name", False, MIA),
        ("Nene", 2403, "box_last_name", False, DEN),
        ("Heat", None, None, True, MIA),
    ]


def test_calls_carry_the_canonical_game_period_clock_and_null_blank_decisions(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "l2m.calls",
        [
            call("Henry Walker", decision="CC"),
            call("Henry Walker", decision="IC", minute=0, second=5.5),
            call("Henry Walker", decision="INC", period="Q5", minute=2, second=0.0),
            call("Henry Walker", decision="", period="Q5", minute=0, second=1.0),
        ],
    )

    build_models(con, *MODELS)

    assert rows(
        con,
        "SELECT season, period, seconds_remaining, decision FROM nba.l2m_calls "
        "ORDER BY period, seconds_remaining DESC",
    ) == [
        (2015, 4, 90.0, "CC"),
        (2015, 4, 5.5, "IC"),
        (2015, 5, 120.0, "INC"),
        (2015, 5, 1.0, None),
    ]
    assert rows(
        con,
        "SELECT game_id, calls, correct_calls, incorrect_calls, correct_non_calls, "
        "incorrect_non_calls FROM nba.l2m_games",
    ) == [(GAME, 4, 1, 1, 0, 1)]


def test_officiating_gates_flag_unknown_games_unknown_decisions_and_low_resolution(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(con, "l2m.calls", [call("Henry Walker")])
    build_models(con, *MODELS)
    names = (
        "officiating_l2m_games_exist",
        "officiating_decisions_in_the_closed_set",
        "officiating_committing_players_resolve_over_99_5_percent",
    )
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)

    insert(con, "l2m.calls", [{**call("Nobody Atall", decision="XX"), "gid": "0029999999"}])
    build_models(con, *MODELS)

    assert check(con, gate("officiating_l2m_games_exist")).sample == [{"game_id": "0029999999"}]
    assert check(con, gate("officiating_decisions_in_the_closed_set")).sample == [
        {"decision": "XX", "n": 1}
    ]
    assert check(con, gate("officiating_committing_players_resolve_over_99_5_percent")).sample == [
        {"unresolved": 1, "named": 2}
    ]


def official(official_id: int, first: str, last: str, game: str = GAME, season: int = 2015) -> dict:
    return {
        "game_id": game,
        "official_id": official_id,
        "first_name": first,
        "last_name": last,
        "jersey_num": "12 ",
        "season": season,
    }


def test_game_officials_name_each_crew_and_officials_span_their_seasons(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_officials",
        [official(1146, "Tommy", "Nunez Jr."), official(1830, "Justin", "Van Duyne")],
    )
    build_models(con, *MODELS)

    assert rows(con, "SELECT game_id, name, jersey_num FROM nba.game_officials ORDER BY 2") == [
        (GAME, "Justin Van Duyne", "12"),
        (GAME, "Tommy Nunez Jr.", "12"),
    ]
    assert rows(con, "SELECT official_id, name, from_season, games FROM nba.officials") == [
        (1146, "Tommy Nunez Jr.", 2015, 1),
        (1830, "Justin Van Duyne", 2015, 1),
    ]


def test_officials_gates_flag_duplicates_unknown_games_and_espn_disagreement(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(con, "sdv.nba_schedule_crosswalk", [{"nba_game_id": GAME, "espn_game_id": "400578"}])
    insert(
        con,
        "sdv.espn_nba_officials",
        [
            {"game_id": 400578, "official_display_name": "Tommy Nunez Jr.", "season": 2015},
            {"game_id": 400578, "official_display_name": "Justin Van Duyne", "season": 2015},
        ],
    )
    insert(
        con,
        "sdv.nba_stats_officials",
        [official(1146, "Tommy", "Nunez Jr."), official(1830, "Justin", "Van Duyne")],
    )
    build_models(con, *MODELS)
    names = (
        "officiating_game_officials_key_unique",
        "officiating_game_officials_games_exist",
        "officiating_game_officials_agree_with_espn_over_99_percent",
    )
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)

    insert(
        con,
        "sdv.nba_stats_officials",
        [
            official(1146, "Tommy", "Nunez Jr."),
            official(7, "Eli", "Roe"),
            official(9, "No", "Game", game="0029999999"),
        ],
    )
    build_models(con, *MODELS)

    assert check(con, gate(names[0])).sample == [{"game_id": GAME, "official_id": 1146, "n": 2}]
    assert check(con, gate(names[1])).sample == [{"game_id": "0029999999"}]
    assert check(con, gate(names[2])).sample == [{"unnamed": 1, "officials": 4}]
