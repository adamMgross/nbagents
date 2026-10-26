from __future__ import annotations

from collections.abc import Iterator

import duckdb
import pytest

from nbalake.curate import check
from nbalake.lake import Root
from nbalake.models import ALL
from tests.curated import (
    build_models,
    empty_lake,
    files_read,
    gate,
    insert,
    rows,
    sources,
    table_rows_equal_its_sql,
)

GAMES = ("franchises", "team_seasons", "games")
EVENTS = ("pbp_actors", "pbp_qualifiers", "pbp")
MODELS = (
    "franchises",
    "team_seasons",
    "games",
    "espn_bref_links",
    "player_xref",
    "player_box",
    "pbp_actors",
    "pbp_qualifiers",
    "pbp",
    "possessions",
    "shots",
    "lineup_stints",
    "pbp_espn",
)
BOS, LAL = 1610612738, 1610612747
GAME = "0022300001"
LEBRON, TATUM, CURRY = 2544, 1628369, 201939


def event(
    order: int,
    period: int,
    seconds: float,
    home: str = "",
    away: str = "",
    person: int = 2544,
    kind: str = "missed_shot",
    **extra: object,
) -> dict:
    return {
        "game_id": GAME,
        "season": 2024,
        "order_index": order,
        "action_number": order,
        "period": period,
        "seconds_remaining": seconds,
        "score_home": home,
        "score_away": away,
        "person_id": person,
        "event_type": kind,
        "description": f"event {order}",
        **extra,
    }


def v2(event_number: int, kind: int, second: int, game: str = GAME, season: int = 2024) -> dict:
    return {
        "GAME_ID": int(game),
        "EVENTNUM": event_number,
        "EVENTMSGTYPE": kind,
        "PLAYER2_ID": second,
        "season": season,
    }


def cdn(action_number: int, kind: str = "2pt", period: int = 1, **extra: object) -> dict:
    return {
        "gameId": int(GAME),
        "actionNumber": action_number,
        "actionType": kind,
        "period": period,
        "season": 2024,
        "season_type": "regular",
        **extra,
    }


def secondary(action_number: int, person: int, word: str, order: int) -> dict:
    return event(
        order,
        1,
        600.0,
        person=person,
        action_number=action_number,
        action_type="",
        description=f"Player {word} (1 {word[:3]})",
    )


@pytest.fixture
def con(root: Root) -> Iterator[duckdb.DuckDBPyConnection]:
    con = empty_lake(root, sources(*MODELS, gate_prefix="events_"))
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            {
                "game_id": GAME,
                "season": 2024,
                "season_type": "regular-season",
                "game_date": "2023-10-24",
                "home_team_id": BOS,
                "away_team_id": LAL,
                "home_pts": 130,
                "away_pts": 98,
            }
        ],
    )
    insert(
        con,
        "sdv.nba_stats_player_boxscores",
        [
            {
                "game_id": GAME,
                "team_id": LAL,
                "person_id": 2544,
                "first_name": "LeBron",
                "family_name": "James",
                "season": 2024,
                "minutes": "30:00",
                "assists": 1,
                "steals": 0,
                "blocks": 0,
            }
        ],
    )
    yield con
    con.close()


def test_pbp_fills_the_running_score_forward_and_flags_garbage_time_on_the_margin_before_the_event(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_pbp",
        [
            event(1, 1, 720.0, "0", "0", person=0, kind="period"),
            event(2, 4, 600.0, "110", "84"),
            event(3, 4, 541.0),
            event(4, 4, 540.0, person=BOS, kind="rebound"),
            event(5, 4, 400.0, "111", "90"),
            event(6, 4, 360.0),
            event(7, 5, 100.0),
        ],
    )

    build_models(con, *EVENTS)

    assert rows(
        con,
        "SELECT order_index, player_id, score_home, game_seconds_elapsed, garbage_time, "
        "description FROM nba.pbp ORDER BY order_index",
    ) == [
        (1, None, 0, 0.0, False, "event 1"),
        (2, 2544, 110, 2280.0, False, "event 2"),
        (3, 2544, None, 2339.0, False, "event 3"),
        (4, None, None, 2340.0, True, "event 4"),
        (5, 2544, 111, 2480.0, True, "event 5"),
        (6, 2544, None, 2520.0, True, "event 6"),
        (7, 2544, None, 3080.0, True, "event 7"),
    ]


def test_pbp_is_built_by_season_into_one_file_per_season(
    con: duckdb.DuckDBPyConnection,
) -> None:
    con.execute("ALTER TABLE sdv.nba_stats_pbp SET PARTITIONED BY (season)")
    older = {"game_id": "0022200001", "season": 2023}
    insert(
        con,
        "sdv.nba_stats_pbp",
        [event(1, 1, 700.0, action_type="Turnover"), secondary(1, TATUM, "STEAL", 2)],
    )
    insert(
        con,
        "sdv.nba_stats_pbp",
        [
            {**event(1, 1, 700.0, action_type="Turnover"), **older},
            {**secondary(1, TATUM, "STEAL", 2), **older},
        ],
    )
    build_models(con, *EVENTS)

    assert files_read(con, "SELECT * FROM nba.pbp") == 2
    assert files_read(con, "SELECT * FROM nba.pbp WHERE season = 2024") == 1


@pytest.mark.parametrize(
    ("view", "staged"),
    [
        ("possessions", "sdv.nba_stats_possessions"),
        ("shots", "sdv.nba_stats_shots"),
        ("lineup_stints", "sdv.nba_stats_game_lineups"),
    ],
)
def test_a_season_filter_on_an_event_view_reads_one_staged_file_of_three(
    con: duckdb.DuckDBPyConnection, view: str, staged: str
) -> None:
    for season in (2001, 2002, 2003):
        insert(con, staged, [{"season": season, "game_id": f"002{season % 100:02d}00001"}])
    build_models(con, "possessions", "shots", "lineup_stints")

    assert files_read(con, f"SELECT * FROM nba.{view} WHERE season = 2002") == 1


def test_pbp_and_pbp_actors_built_by_season_equal_their_sql_run_whole(
    con: duckdb.DuckDBPyConnection,
) -> None:
    older = {"game_id": "0022200001", "season": 2023}
    insert(
        con,
        "sdv.nba_stats_pbp",
        [
            event(1, 1, 700.0, action_type="Turnover"),
            secondary(1, TATUM, "STEAL", 2),
            {**event(1, 1, 700.0, action_type="Turnover"), **older},
            {**secondary(1, TATUM, "STEAL", 2), **older},
        ],
    )
    build_models(con, *EVENTS)

    assert table_rows_equal_its_sql(con, "pbp_actors")
    assert table_rows_equal_its_sql(con, "pbp")
    assert con.execute("SELECT count(DISTINCT season) FROM nba.pbp").fetchall() == [(2,)]


def test_pbp_puts_the_assister_blocker_stealer_and_fouled_player_on_the_primary_event_only(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_pbp",
        [
            event(1, 1, 700.0, person=CURRY, action_type="Made Shot"),
            event(2, 1, 690.0, person=LEBRON, action_type="Missed Shot"),
            secondary(2, TATUM, "BLOCK", 3),
            event(4, 1, 680.0, person=LEBRON, action_number=3, action_type="Turnover   "),
            secondary(3, TATUM, "STEAL", 5),
            event(6, 1, 670.0, person=TATUM, action_number=4, action_type="Foul"),
            event(7, 1, 660.0, person=LEBRON, action_number=5, action_type="Missed Shot"),
            secondary(5, 0, "BLOCK", 8),
        ],
    )
    insert(
        con,
        "shuf.nbastats",
        [v2(1, 1, LEBRON), v2(1, 1, LEBRON), v2(4, 6, LEBRON), v2(6, 6, LAL), v2(7, 1, 0)],
    )

    build_models(con, *EVENTS)

    assert rows(
        con,
        "SELECT action_number, trim(action_type), assist_player_id, block_player_id, "
        "steal_player_id, fouled_player_id FROM nba.pbp ORDER BY order_index",
    ) == [
        (1, "Made Shot", LEBRON, None, None, None),
        (2, "Missed Shot", None, TATUM, None, None),
        (2, "", None, None, None, None),
        (3, "Turnover", None, None, TATUM, None),
        (3, "", None, None, None, None),
        (4, "Foul", None, None, None, LEBRON),
        (5, "Missed Shot", None, None, None, None),
        (5, "", None, None, None, None),
    ]
    assert rows(con, "SELECT count(*) FROM nba.pbp_actors") == [(4,)]


def test_pbp_grain_is_one_row_per_order_index_since_block_and_steal_rows_repeat_action_number(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_pbp",
        [
            event(1, 1, 690.0, action_type="Missed Shot"),
            secondary(1, TATUM, "BLOCK", 2),
            event(3, 1, 680.0, action_number=2, action_type="Turnover"),
            secondary(2, TATUM, "STEAL", 4),
        ],
    )
    build_models(con, *EVENTS)
    grain = ", ".join(next(m.grain for m in ALL if m.name == "pbp"))

    assert grain == "game_id, order_index"
    assert rows(con, f"SELECT count(*), count(DISTINCT ({grain})) FROM nba.pbp") == [(4, 4)]
    assert rows(con, "SELECT count(DISTINCT (game_id, action_number)) FROM nba.pbp") == [(2,)]


def test_pbp_actor_gates_pass_on_consistent_actors_and_flag_each_violation(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_player_boxscores",
        [
            {
                "game_id": GAME,
                "team_id": BOS,
                "person_id": CURRY,
                "first_name": "Stephen",
                "family_name": "Curry",
                "season": 2024,
                "minutes": "30:00",
                "assists": 0,
                "steals": 0,
                "blocks": 0,
            }
        ],
    )
    insert(con, "sdv.nba_stats_pbp", [event(1, 1, 700.0, person=CURRY, action_type="Made Shot")])
    insert(con, "shuf.nbastats", [v2(1, 1, LEBRON)])
    build_models(con, *MODELS)
    names = (
        "events_pbp_actors_match_an_event_under_0_01_percent",
        "events_pbp_actors_resolve_under_0_01_percent",
        "events_pbp_actor_counts_disagree_with_box_under_0_1_percent",
    )
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)

    insert(
        con,
        "sdv.nba_stats_pbp",
        [
            event(2, 1, 690.0, person=CURRY, action_type="Turnover"),
            secondary(2, LEBRON, "STEAL", 3),
        ],
    )
    insert(con, "shuf.nbastats", [v2(9, 1, 775)])
    preseason = "0012300001"
    insert(
        con,
        "sdv.nba_stats_schedules",
        [{"game_id": preseason, "season": 2024, "season_type": "preseason"}],
    )
    insert(
        con,
        "sdv.nba_stats_pbp",
        [
            {**event(1, 1, 700.0, action_type="Turnover"), "game_id": preseason},
            {**secondary(1, 1630000, "STEAL", 2), "game_id": preseason},
        ],
    )
    build_models(con, "games", "pbp_actors")

    assert check(con, gate(names[0])).sample == [{"unmatched": 1, "actors": 4}]
    assert check(con, gate(names[1])).sample == [{"unresolved": 1, "actor_ids": 3}]
    assert check(con, gate(names[2])).sample == [{"disagree": 1, "player_games": 2}]


def test_views_read_staged_rows_without_a_rebuild(con: duckdb.DuckDBPyConnection) -> None:
    build_models(con, *MODELS)
    insert(
        con,
        "sdv.nba_stats_shots",
        [
            {
                "game_id": GAME,
                "season": 2024,
                "person_id": 2544,
                "shot_result": "Made",
                "x_legacy": -234,
                "y_legacy": 18,
            }
        ],
    )

    assert rows(
        con,
        "SELECT table_type FROM information_schema.tables "
        "WHERE table_schema = 'nba' AND table_name = 'shots'",
    ) == [("VIEW",)]
    assert rows(con, "SELECT player_id, made, x_feet, y_feet, season FROM nba.shots") == [
        (2544, True, -23.4, 1.8, 2024)
    ]


def test_espn_pbp_gets_the_canonical_game_and_nulls_the_coordinate_sentinels(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(con, "sdv.nba_schedule_crosswalk", [{"nba_game_id": GAME, "espn_game_id": "401584689"}])
    insert(
        con,
        "sdv.espn_nba_pbp",
        [
            {
                "game_id": 401584689,
                "sequence_number": 1,
                "coordinate_x": -214748340.0,
                "coordinate_y": 214748406.75,
                "coordinate_x_raw": 25.0,
                "coordinate_y_raw": 5.0,
            },
            {"game_id": 999, "sequence_number": 1, "coordinate_x": 3.5, "coordinate_y": -40.0},
        ],
    )

    build_models(con, *GAMES, "pbp_espn")

    assert rows(
        con,
        "SELECT espn_game_id, game_id, coordinate_x, coordinate_y, coordinate_x_raw "
        "FROM nba.pbp_espn ORDER BY 1",
    ) == [
        (999, None, 3.5, -40.0, None),
        (401584689, GAME, None, None, 25.0),
    ]


def test_events_gates_pass_on_consistent_events_and_flag_each_violation(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_pbp",
        [event(1, 1, 700.0, "0", "2", kind="made_shot", shot_result="Made", is_field_goal=1)],
    )
    insert(
        con,
        "sdv.nba_stats_shots",
        [{"game_id": GAME, "season": 2024, "person_id": 2544, "shot_result": "Made"}],
    )
    build_models(con, *MODELS)
    names = (
        "events_pbp_games_exist",
        "events_shot_chart_makes_match_pbp",
        "events_competitive_shooters_resolve_under_0_01_percent",
        "events_espn_pbp_games_resolve_under_0_1_percent",
    )
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)

    insert(
        con,
        "sdv.nba_stats_pbp",
        [event(2, 1, 690.0, person=775, kind="made_shot", shot_result="Made", is_field_goal=1)],
    )
    insert(con, "sdv.nba_stats_pbp", [{**event(1, 1, 700.0), "game_id": "0029999999"}])
    insert(con, "sdv.espn_nba_pbp", [{"game_id": 999, "sequence_number": 1}])
    build_models(con, *MODELS)

    assert check(con, gate("events_shot_chart_makes_match_pbp")).sample == [
        {"game_id": GAME, "chart_made": 1, "pbp_made": 2}
    ]
    assert check(con, gate("events_pbp_games_exist")).sample == [{"game_id": "0029999999"}]
    assert check(con, gate("events_competitive_shooters_resolve_under_0_01_percent")).sample == [
        {"unresolved": 1, "events": 2}
    ]
    assert check(con, gate("events_espn_pbp_games_resolve_under_0_1_percent")).sample == [
        {"unresolved": 1, "games": 1}
    ]


def test_pbp_carries_the_cdn_qualifiers_and_their_flags_on_the_primary_event_only(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_pbp",
        [
            event(1, 1, 700.0, person=CURRY, action_type="Missed Shot"),
            secondary(1, TATUM, "BLOCK", 2),
            event(3, 1, 690.0, person=TATUM, action_type="Foul"),
        ],
    )
    insert(
        con,
        "shuf.cdnnba",
        [
            cdn(1, qualifiers="pointsinthepaint, fastbreak", descriptor="pullup", officialId=0),
            cdn(3, kind="foul", qualifiers="", descriptor="", officialId=1153),
        ],
    )
    build_models(con, *EVENTS)

    assert rows(
        con,
        "SELECT action_number, action_type, qualifiers, fast_break, second_chance, "
        "points_in_paint, descriptor, official_id FROM nba.pbp ORDER BY order_index",
    ) == [
        (1, "Missed Shot", ["pointsinthepaint", "fastbreak"], True, False, True, "pullup", None),
        (1, "", None, None, None, None, None, None),
        (3, "Foul", [], False, False, False, None, 1153),
    ]


def test_pbp_actors_take_cdn_actors_where_v2_has_none_and_keep_v2_where_both_do(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_pbp",
        [
            event(1, 1, 700.0, person=CURRY, action_type="Made Shot"),
            event(2, 1, 690.0, person=CURRY, action_type="Made Shot"),
        ],
    )
    insert(con, "shuf.nbastats", [v2(1, 1, LEBRON)])
    insert(con, "shuf.cdnnba", [cdn(1, assistPersonId=TATUM), cdn(2, assistPersonId=TATUM)])
    build_models(con, "pbp_actors")

    assert rows(con, "SELECT action_number, assist_player_id FROM nba.pbp_actors ORDER BY 1") == [
        (1, LEBRON),
        (2, TATUM),
    ]


def test_the_cdn_match_gate_flags_cdn_events_that_v3_does_not_have(
    con: duckdb.DuckDBPyConnection,
) -> None:
    name = "events_cdn_events_match_v3_under_0_1_percent"
    insert(con, "sdv.nba_stats_pbp", [event(1, 1, 700.0, action_type="Missed Shot")])
    insert(con, "shuf.cdnnba", [cdn(1), cdn(1, kind="steal")])
    assert check(con, gate(name)).violations == 0

    insert(con, "shuf.cdnnba", [cdn(7, kind="rebound")])

    assert check(con, gate(name)).sample == [{"unmatched": 1, "events": 2}]


def test_espn_pbp_of_a_game_nba_stats_has_not_published_carries_its_minted_game_id(
    con: duckdb.DuckDBPyConnection,
) -> None:
    con.execute("ALTER TABLE sdv.espn_nba_pbp SET PARTITIONED BY (season)")
    insert(
        con,
        "sdv.nba_team_crosswalk",
        [
            {"season": 2024, "espn_team_id": e, "nba_team_id": str(t)}
            for t, e in ((BOS, 2), (LAL, 13))
        ],
    )
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            {
                "game_id": GAME,
                "season": 2024,
                "season_type": "regular-season",
                "game_date": "2023-10-24",
                "home_team_id": BOS,
                "away_team_id": LAL,
                "home_pts": 100,
                "away_pts": 90,
            }
        ],
    )
    insert(
        con,
        "sdv.espn_nba_schedule_master",
        [
            {
                "id": 401584700,
                "date": "2023-10-27T23:30Z",
                "season": 2024,
                "season_type": 2,
                "type_abbreviation": "STD",
                "home_id": 2,
                "away_id": 13,
                "home_score": 110,
                "away_score": 105,
                "status_type_completed": True,
            }
        ],
    )
    insert(con, "sdv.espn_nba_pbp", [{"game_id": 401584700, "sequence_number": 1, "season": 2024}])
    insert(con, "sdv.espn_nba_pbp", [{"game_id": 230101002, "sequence_number": 1, "season": 2023}])
    build_models(con, *GAMES, "pbp_espn")

    assert rows(con, "SELECT game_id FROM nba.pbp_espn WHERE season = 2024") == [("espn401584700",)]
    assert files_read(con, "SELECT * FROM nba.pbp_espn") == 3
    assert files_read(con, "SELECT * FROM nba.pbp_espn WHERE season = 2024") == 2
