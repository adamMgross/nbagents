from __future__ import annotations

from typing import Any

import duckdb
import pytest
from typer.testing import CliRunner

from nbalake.explore import macros, session
from nbalake.explore.cli import app
from nbalake.lake import Root
from nbalake.models import ALL
from tests.curated import build_models, empty_lake, insert, sources

NEEDED = {
    "games",
    "team_seasons",
    "arenas",
    "team_elo",
    "team_games",
    "players",
    "player_box",
    "player_seasons",
    "game_lines",
    "possessions",
    "shots",
    "franchises",
    "teams",
    "espn_bref_links",
    "player_xref",
    "odds_teams",
    "playoff_series",
    "team_season_stats",
    "pbp_actors",
    "pbp_qualifiers",
    "pbp",
    "us_population",
    "player_birthplaces",
}
MODELS = tuple(m.name for m in ALL if m.name in NEEDED)
A, B, C = 1610612744, 1610612739, 1610612760
P, TRADED, STEADY, SHORT = 201939, 1, 2, 3
G1, G2, G3, G4, G5, PRE = "g1", "g2", "g3", "g4", "g5", "pre"
DATES = {G1: "2015-11-01", G4: "2015-11-07", G5: "2015-11-09", PRE: "2015-10-10"}
A_ON = (P, 11, 12, 13, 14)
A_OFF = (16, 11, 12, 13, 14)
B_FIVE = (21, 22, 23, 24, 25)


def game(game_id: str, day: str, home: int, away: int, season_type: str = "regular") -> dict:
    return {
        "game_id": game_id,
        "season": 2016,
        "game_date": day,
        "season_type": season_type,
        "home_team_id": home,
        "away_team_id": away,
        "home_pts": 100,
        "away_pts": 90,
        "winner_team_id": home,
    }


def possession(
    game_id: str,
    offense: int,
    defense: int,
    points: int,
    off5: tuple[int, ...],
    def5: tuple[int, ...],
    counts: bool = True,
) -> dict:
    row: dict[str, object] = {
        "game_id": game_id,
        "season": 2016,
        "offense_team_id": offense,
        "defense_team_id": defense,
        "points": points,
        "count_as_possession": counts,
    }
    row |= {f"off_player_{i + 1}": p for i, p in enumerate(off5)}
    row |= {f"def_player_{i + 1}": p for i, p in enumerate(def5)}
    return row


def shot(player: int, x: int, y: int, value: int, distance: int, made: bool) -> dict:
    return {
        "game_id": G1,
        "season": 2016,
        "person_id": player,
        "x_legacy": x,
        "y_legacy": y,
        "shot_value": value,
        "shot_distance": distance,
        "season_type_id": "2",
        "shot_result": "Made" if made else "Missed",
    }


def team_game(game_id: str, home: bool, margin: int, season_type: str = "regular") -> dict:
    return {
        "game_id": game_id,
        "season": 2016,
        "season_type": season_type,
        "game_date": DATES[game_id],
        "team_id": A,
        "opponent_team_id": B,
        "is_home": home,
        "margin": margin,
        "won": margin > 0,
        "pts": 100,
        "opp_pts": 100 - margin,
    }


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Root:
    root = Root(tmp_path_factory.mktemp("macros") / "lake")
    con = empty_lake(root, sources(*MODELS))
    build_models(con, *MODELS)
    insert(
        con,
        "nba.games",
        [
            game(G1, "2015-11-01", A, B),
            game(G2, "2015-11-03", A, C),
            game(G3, "2015-11-05", A, B),
            game(G4, "2015-11-07", B, A),
            game(G5, "2015-11-09", A, B),
            game(PRE, "2015-10-10", A, B, "preseason"),
        ],
    )
    insert(
        con,
        "nba.team_seasons",
        [
            {"season": 2016, "team_id": t, "abbreviation": a}
            for t, a in ((A, "GSW"), (B, "CLE"), (C, "OKC"))
        ],
    )
    insert(con, "nba.players", [{"player_id": P, "name": "Stephen Curry"}])
    insert(
        con,
        "sdv.nba_stats_possessions",
        [
            possession(G1, A, B, 3, A_ON, B_FIVE),
            possession(G1, A, B, 2, A_ON, B_FIVE),
            possession(G1, A, B, 0, A_OFF, B_FIVE),
            possession(G1, B, A, 1, B_FIVE, A_ON),
            possession(G1, B, A, 2, B_FIVE, A_OFF),
            possession(G1, B, A, 0, B_FIVE, A_ON),
            possession(G1, A, B, 3, A_ON, B_FIVE, counts=False),
            possession(G2, A, C, 2, A_OFF, B_FIVE),
            possession(PRE, A, B, 3, A_ON, B_FIVE),
        ],
    )
    insert(
        con,
        "nba.team_games",
        [
            team_game(G1, True, 10),
            team_game(G4, False, -3),
            team_game(G5, True, 2),
            team_game(PRE, True, 30, "preseason"),
        ],
    )
    insert(
        con,
        "nba.game_lines",
        [
            {"game_id": G1, "season": 2016, "source": "s", "book": "x", "home_spread": -5.0},
            {"game_id": G1, "season": 2016, "source": "s", "book": "y", "home_spread": -6.0},
            {"game_id": G4, "season": 2016, "source": "s", "book": "x", "home_spread": -4.0},
            {"game_id": G5, "season": 2016, "source": "s", "book": "x", "home_spread": -2.0},
            {"game_id": PRE, "season": 2016, "source": "s", "book": "x", "home_spread": -1.0},
        ],
    )
    insert(
        con,
        "nba.player_box",
        [
            {
                "game_id": G1,
                "season": 2016,
                "team_id": A,
                "player_id": P,
                "seconds": 2160,
                "pts": 30,
                "played": True,
            },
            {
                "game_id": PRE,
                "season": 2016,
                "team_id": A,
                "player_id": P,
                "seconds": 600,
                "pts": 9,
                "played": True,
            },
            {
                "game_id": G5,
                "season": 2016,
                "team_id": A,
                "player_id": P,
                "pts": 0,
                "played": False,
            },
        ],
    )
    insert(
        con,
        "nba.player_seasons",
        [
            {
                "season": 2016,
                "lg": "NBA",
                "player_id": TRADED,
                "player": "Traded",
                "bref_team": "2TM",
                "multi_team": True,
                "g": 70,
                "pts": 1400,
                "pts_per_100_poss": 30.0,
            },
            {
                "season": 2016,
                "lg": "NBA",
                "player_id": TRADED,
                "player": "Traded",
                "bref_team": "GSW",
                "team_id": A,
                "multi_team": False,
                "g": 40,
                "pts": 800,
                "pts_per_100_poss": 30.0,
            },
            {
                "season": 2016,
                "lg": "NBA",
                "player_id": TRADED,
                "player": "Traded",
                "bref_team": "CLE",
                "team_id": B,
                "multi_team": False,
                "g": 30,
                "pts": 600,
                "pts_per_100_poss": 30.0,
            },
            {
                "season": 2016,
                "lg": "NBA",
                "player_id": STEADY,
                "player": "Steady",
                "bref_team": "GSW",
                "team_id": A,
                "multi_team": False,
                "g": 60,
                "pts": 1300,
                "pts_per_100_poss": 99.0,
            },
            {
                "season": 2016,
                "lg": "NBA",
                "player_id": SHORT,
                "player": "Short",
                "bref_team": "GSW",
                "team_id": A,
                "multi_team": False,
                "g": 20,
                "pts": 2000,
                "pts_per_100_poss": 50.0,
            },
            {
                "season": 2016,
                "lg": "ABA",
                "player_id": 4,
                "player": "Other league",
                "bref_team": "X",
                "multi_team": False,
                "g": 80,
                "pts": 3000,
            },
        ],
    )
    insert(
        con,
        "sdv.nba_stats_shots",
        [
            shot(P, 230, 50, 3, 23, True),
            shot(P, 0, 260, 3, 26, False),
            shot(P, 0, 10, 2, 1, True),
            shot(P, 50, 100, 2, 11, False),
            shot(P, 150, 150, 2, 21, True),
            shot(99, 0, 5, 2, 0, False),
        ],
    )
    con.close()
    return root


@pytest.fixture
def con(root: Root) -> duckdb.DuckDBPyConnection:
    return session.connect(root)


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    con.execute(sql)
    names = [d[0] for d in con.description or ()]
    return [dict(zip(names, r, strict=True)) for r in con.fetchall()]


def test_per_100_scales_points_and_is_null_for_zero_possessions(
    con: duckdb.DuckDBPyConnection,
) -> None:
    assert con.execute("SELECT per_100(5, 2), per_100(5, 0)").fetchall() == [(250.0, None)]


def test_on_off_rates_counted_possessions_in_games_the_player_played(
    con: duckdb.DuckDBPyConnection,
) -> None:
    """G2 has no possession with the player on the floor, so it counts as neither on nor off.

    The uncounted possession and the preseason game are excluded too. Without those filters
    off_rating would include G2's 2 points and on_rating the preseason 3.
    """
    found = rows(con, f"FROM on_off({P}, 2016)")

    assert [
        (
            r["on_court"],
            r["off_possessions"],
            r["off_rating"],
            r["def_possessions"],
            r["def_rating"],
            r["net_rating"],
        )
        for r in found
    ] == [
        (True, 2, 250.0, 2, 50.0, 200.0),
        (False, 1, 0.0, 1, 200.0, -200.0),
    ]


def test_team_games_of_skips_preseason_and_grades_the_team_side_of_the_median_spread(
    con: duckdb.DuckDBPyConnection,
) -> None:
    found = rows(con, f"FROM team_games_of({A}, 2016)")

    assert [(r["game_id"], r["spread"], r["ats"]) for r in found] == [
        (G1, -5.5, "cover"),
        (G4, 4.0, "cover"),
        (G5, -2.0, "push"),
    ]
    assert rows(con, f"FROM team_games_of({A}, 2016, season_type := NULL)")[0]["game_id"] == PRE


def test_against_the_spread_splits_by_venue_and_role_with_subtotals(
    con: duckdb.DuckDBPyConnection,
) -> None:
    found = {(r["venue"], r["role"]): r for r in rows(con, f"FROM against_the_spread({A}, 2016)")}

    assert set(found) == {
        ("all", "all"),
        ("all", "favorite"),
        ("all", "underdog"),
        ("away", "all"),
        ("away", "underdog"),
        ("home", "all"),
        ("home", "favorite"),
    }
    total = found[("all", "all")]
    assert (total["games"], total["covers"], total["losses"], total["pushes"]) == (3, 2, 0, 1)
    assert total["cover_rate"] == 1.0
    assert found[("home", "favorite")]["pushes"] == 1


def test_player_games_returns_the_regular_season_line_with_opponent_and_spread(
    con: duckdb.DuckDBPyConnection,
) -> None:
    (found,) = rows(con, f"FROM player_games({P}, 2016)")

    assert (found["game_id"], found["team"], found["opponent"], found["home"], found["won"]) == (
        G1,
        "GSW",
        "CLE",
        True,
        True,
    )
    assert (found["minutes"], found["pts"], found["spread"]) == (36.0, 30, -5.5)
    assert len(rows(con, f"FROM player_games({P}, season_type := NULL)")) == 2
    assert len(rows(con, f"FROM player_games({P}, 2016, include_dnp := true)")) == 2


def test_lineups_rates_each_five_and_drops_units_under_min_possessions_on_either_side(
    con: duckdb.DuckDBPyConnection,
) -> None:
    every = rows(con, f"FROM lineups({A}, 2016, 1)")
    (top,) = rows(con, f"FROM lineups({A}, 2016, 2)")

    assert {tuple(r["player_ids"]) for r in every} == {tuple(sorted(A_ON)), tuple(sorted(A_OFF))}
    assert (top["off_possessions"], top["def_possessions"], top["net_rating"]) == (2, 2, 200.0)
    assert top["players"].startswith("11, 12, 13, 14, Stephen Curry")


def test_lineups_with_no_team_rates_every_team(con: duckdb.DuckDBPyConnection) -> None:
    teams = {r["team"] for r in rows(con, "FROM lineups(NULL, 2016, 1)")}

    assert teams == {"GSW", "CLE"}, "OKC has offense in G2 and no defense, so no unit qualifies"


def test_shot_zones_classify_by_coordinates_and_compare_with_the_league(
    con: duckdb.DuckDBPyConnection,
) -> None:
    found = {r["zone"]: r for r in rows(con, f"FROM shot_zones({P}, 2016)")}

    assert {z: (r["attempts"], r["made"]) for z, r in found.items()} == {
        "corner 3": (1, 1),
        "above the break 3": (1, 0),
        "restricted area": (1, 1),
        "paint": (1, 0),
        "midrange": (1, 1),
    }
    assert found["restricted area"]["league_fg_pct"] == 0.5
    assert found["corner 3"]["share"] == 0.2


def test_leaders_uses_the_traded_players_total_row_and_respects_min_games(
    con: duckdb.DuckDBPyConnection,
) -> None:
    totals = rows(con, "FROM leaders('pts', 2016)")
    per_game = rows(con, "FROM leaders('pts', 2016, per_game := true)")

    assert [(r["player"], r["team"], r["value"]) for r in totals] == [
        ("Traded", "2TM", 1400),
        ("Steady", "GSW", 1300),
    ]
    assert [r["player"] for r in per_game] == ["Steady", "Traded"]


def test_leaders_matches_the_stat_name_exactly(con: duckdb.DuckDBPyConnection) -> None:
    found = rows(con, "FROM leaders('pts_per_100_poss', 2016)")

    assert [r["value"] for r in found] == [99.0, 30.0]


def test_every_macro_example_runs(con: duckdb.DuckDBPyConnection) -> None:
    for m in macros.shipped():
        con.execute(m.example).fetchall()


def test_nba_macros_lists_every_macro_with_its_example(root: Root) -> None:
    out = CliRunner().invoke(app, ["macros"]).stdout

    for m in macros.shipped():
        assert f"## {m.signature}" in out
        assert m.example in out
    assert len(macros.shipped()) == 27


def made(name: str, body: str) -> macros.Macro:
    sql = f"CREATE OR REPLACE TEMP MACRO {name}() AS TABLE {body}"
    return macros.Macro(name, f"{name}()", "", "", sql, body)


def test_macros_load_after_the_macros_they_call_whatever_their_names() -> None:
    found = [
        made("a_career", "SELECT * FROM b_season()"),
        made("b_season", "SELECT * FROM c_game()"),
        made("c_game", "SELECT 1 AS x"),
        made("c_game_extra", "SELECT 2 AS x"),
    ]

    ordered = macros.in_load_order(found)

    assert [m.name for m in ordered] == ["c_game", "c_game_extra", "b_season", "a_career"]
    con = duckdb.connect()
    for m in ordered:
        con.execute(m.sql)
    assert con.sql("FROM a_career()").fetchall() == [(1,)]


CHAIN = [
    made("a_career", "SELECT * FROM b_season()"),
    made("b_season", "SELECT * FROM c_game() JOIN c_game_extra () USING (x)"),
    made("c_game", "SELECT 1 AS x"),
    made("c_game_extra", "SELECT 1 AS x"),
    made("d_unused", "SELECT 3 AS x"),
]


@pytest.mark.parametrize(
    ("queries", "names"),
    [
        (["from a_career() limit 5"], ["a_career", "b_season", "c_game", "c_game_extra"]),
        (["from c_game()", "from a_career()"], ["c_game", "a_career", "b_season", "c_game_extra"]),
        (["from c_game_extra()"], ["c_game_extra"]),
        (["select 'a_career()' as s from nba.games"], []),
    ],
)
def test_called_by_follows_calls_through_macros_callers_first_each_once(
    queries: list[str], names: list[str]
) -> None:
    assert [m.name for m in macros.called_by(queries, CHAIN)] == names


def test_called_by_resolves_a_metric_down_to_the_elo_macro() -> None:
    names = [
        m.name for m in macros.called_by(["from career_postseason() limit 30"], macros.shipped())
    ]

    assert names == [
        "career_postseason",
        "postseason_season_credit",
        "postseason_game_credit",
        "postseason_team_credit",
        "elo_game_prob",
    ]


def test_every_macro_loads_on_a_lake_without_the_tables_it_reads() -> None:
    con = duckdb.connect()
    con.execute("CREATE SCHEMA nba")

    for m in macros.shipped():
        con.execute(m.sql)
