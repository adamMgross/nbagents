from __future__ import annotations

import csv
import math
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import duckdb
import pytest

from nbalake.curate import check
from nbalake.lake import Root
from tests.curated import build_models, empty_lake, gate, insert, rows

TABLES = (
    "bref.team_summaries",
    "sdv.nba_team_crosswalk",
    "sdv.nba_team_group_seasons",
    "sdv.nba_stats_schedules",
    "sdv.nba_stats_team_boxscores",
    "sdv.espn_nba_schedule_master",
    "sdv.nba_schedule_crosswalk",
    "fte.elo",
)
MODELS = (
    "arenas",
    "franchises",
    "team_seasons",
    "teams",
    "games",
    "team_elo",
    "team_games",
    "games_cross_source",
)
BOS, LAL, CHI = 1610612738, 1610612747, 1610612741
ESPN = {BOS: 2, LAL: 13, CHI: 4}


def schedule(
    game_id: str,
    game_date: str,
    home: int,
    away: int,
    pts: tuple[int, int] | None,
    season: int = 2001,
    season_type: str = "regular-season",
) -> dict:
    return {
        "game_id": game_id,
        "season": season,
        "season_type": season_type,
        "game_date": game_date,
        "home_team_id": home,
        "away_team_id": away,
        "home_pts": pts[0] if pts else None,
        "away_pts": pts[1] if pts else None,
    }


def espn(
    espn_id: int,
    utc: str,
    home: int,
    away: int,
    score: tuple[int, int],
    season: int = 2001,
    **extra: object,
) -> dict:
    return {
        "id": espn_id,
        "date": utc,
        "season": season,
        "season_type": 2,
        "type_abbreviation": "STD",
        "home_id": ESPN[home],
        "away_id": ESPN[away],
        "home_score": score[0],
        "away_score": score[1],
        "status_type_completed": True,
        "neutral_site": False,
        **extra,
    }


def elo(
    game_id: str,
    day: str,
    season: int,
    team: str,
    opp: str,
    pts: int,
    opp_pts: int,
    copy: int = 0,
    location: str = "H",
    playoffs: int = 0,
    **extra: object,
) -> dict:
    return {
        "game_id": game_id,
        "date_game": day,
        "year_id": season,
        "lg_id": "NBA",
        "_iscopy": copy,
        "is_playoffs": playoffs,
        "team_id": team,
        "opp_id": opp,
        "pts": pts,
        "opp_pts": opp_pts,
        "game_location": location,
        **extra,
    }


@pytest.fixture
def con(root: Root) -> Iterator[duckdb.DuckDBPyConnection]:
    con = empty_lake(root, TABLES)
    insert(
        con,
        "sdv.nba_team_crosswalk",
        [
            {"season": s, "espn_team_id": ESPN[t], "nba_team_id": str(t)}
            for t in ESPN
            for s in (1947, 1996, 2001)
        ],
    )
    yield con
    con.close()


def game(con: duckdb.DuckDBPyConnection, game_id: str, *cols: str) -> tuple:
    return rows(con, f"SELECT {', '.join(cols)} FROM nba.games WHERE game_id = ?", [game_id])[0]


def test_nba_era_game_carries_espn_and_fte_ids_venue_and_a_normalized_season_type(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con, "sdv.nba_stats_schedules", [schedule("0020000500", "2001-01-05", BOS, LAL, (101, 99))]
    )
    insert(
        con,
        "sdv.nba_schedule_crosswalk",
        [{"nba_game_id": "0020000500", "espn_game_id": "210105002"}],
    )
    insert(
        con,
        "sdv.espn_nba_schedule_master",
        [
            espn(
                210105002,
                "2001-01-06T00:30Z",
                BOS,
                LAL,
                (101, 99),
                attendance=18624.0,
                venue_full_name="FleetCenter",
            )
        ],
    )
    insert(con, "fte.elo", [elo("200101050BOS", "2001-01-05", 2001, "BOS", "LAL", 101, 99)])

    build_models(con, *MODELS)

    assert game(
        con,
        "0020000500",
        "season",
        "season_type",
        "lg",
        "game_date",
        "winner_team_id",
        "espn_game_id",
        "fte_game_id",
        "attendance",
        "venue",
        "source",
    ) == (
        2001,
        "regular",
        "NBA",
        date(2001, 1, 5),
        BOS,
        210105002,
        "200101050BOS",
        18624,
        "FleetCenter",
        "nba",
    )


def test_pre_1997_games_come_from_elo_with_franchise_ids_and_league_labels(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "fte.elo",
        [
            elo("194611010TRH", "1946-11-01", 1947, "TRH", "NYK", 66, 68),
            elo("194611010TRH", "1946-11-01", 1947, "NYK", "TRH", 68, 66, copy=1, location="A"),
            elo("197205010LAL", "1972-05-01", 1972, "LAL", "NYK", 114, 100, playoffs=1),
            elo("199001010BOS", "1990-01-01", 1990, "BOS", "CHI", 100, 100, location="N"),
        ],
    )

    build_models(con, *MODELS)

    assert rows(
        con,
        "SELECT game_id, lg, season_type, home_team_id, away_team_id, winner_team_id, "
        "neutral_site, source FROM nba.games ORDER BY game_date",
    ) == [
        ("194611010TRH", "BAA", "regular", 800000013, 1610612752, 1610612752, False, "fte"),
        ("197205010LAL", "NBA", "playoffs", LAL, 1610612752, LAL, False, "fte"),
        ("199001010BOS", "NBA", "regular", BOS, CHI, None, True, "fte"),
    ]


def test_espn_games_match_on_the_eastern_date_and_ignore_zero_score_placeholders(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_schedules",
        [schedule("0029900100", "1999-11-03", CHI, BOS, (74, 84), season=2000)],
    )
    insert(
        con,
        "sdv.espn_nba_schedule_master",
        [
            espn(191103004, "1999-11-04T03:30Z", CHI, BOS, (74, 84), season=2000),
            espn(400217505, "1999-11-03T17:00Z", CHI, BOS, (0, 0), season=2000),
        ],
    )
    insert(
        con,
        "sdv.nba_team_crosswalk",
        [{"season": 2000, "espn_team_id": ESPN[t], "nba_team_id": str(t)} for t in ESPN],
    )

    build_models(con, *MODELS)

    assert game(con, "0029900100", "espn_game_id") == (191103004,)
    assert rows(con, "SELECT issue, source_id, detail FROM nba.games_cross_source") == [
        ("espn_unmatched", "400217505", "completed with a 0-0 placeholder score")
    ]


def test_schedule_rows_without_teams_are_reported_not_published_and_unknown_opponents_are_null(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            schedule("0040401000", "2005-06-27", 0, 0, None, season=2005, season_type="playoffs"),
            schedule(
                "0019900002", "1999-10-12", 0, BOS, None, season=2000, season_type="preseason"
            ),
        ],
    )

    build_models(con, *MODELS)

    assert rows(con, "SELECT game_id, home_team_id, away_team_id FROM nba.games") == [
        ("0019900002", None, BOS)
    ]
    assert rows(con, "SELECT issue, game_id, detail FROM nba.games_cross_source") == [
        ("nba_without_teams", "0040401000", "playoffs")
    ]


def test_team_games_count_rest_over_competitive_games_and_carry_elo(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            schedule("0010000001", "2000-10-20", BOS, LAL, (90, 80), season_type="preseason"),
            schedule("0020000001", "2000-11-01", BOS, LAL, (100, 90)),
            schedule("0020000002", "2000-11-02", CHI, BOS, (95, 99)),
            schedule("0020000003", "2000-11-05", BOS, CHI, (101, 102)),
            schedule("0020000004", "2000-11-10", LAL, BOS, (88, 92)),
        ],
    )
    insert(
        con,
        "fte.elo",
        [
            elo(
                "200011010BOS",
                "2000-11-01",
                2001,
                "BOS",
                "LAL",
                100,
                90,
                elo_i=1500.0,
                elo_n=1510.0,
                forecast=0.64,
            ),
            elo(
                "200011010BOS",
                "2000-11-01",
                2001,
                "LAL",
                "BOS",
                90,
                100,
                copy=1,
                location="A",
                elo_i=1550.0,
                elo_n=1540.0,
                forecast=0.36,
            ),
        ],
    )

    build_models(con, *MODELS)

    assert rows(
        con,
        "SELECT game_id, is_home, won, margin, rest_days, back_to_back, games_last_7_days, "
        "season_game_number, elo_source "
        "FROM nba.team_games WHERE team_id = ? ORDER BY game_date",
        [BOS],
    ) == [
        ("0010000001", True, True, 10, None, None, None, 1, None),
        ("0020000001", True, True, 10, None, None, 0, 1, "fte"),
        ("0020000002", False, True, 4, 1, True, 1, 2, "lake"),
        ("0020000003", True, False, -1, 3, False, 2, 3, "lake"),
        ("0020000004", False, True, 4, 5, False, 1, 4, "lake"),
    ]
    assert rows(
        con,
        "SELECT elo_pre, elo_post, elo_win_prob FROM nba.team_games "
        "WHERE game_id = '0020000001' AND team_id = ?",
        [BOS],
    ) == [(1500.0, 1510.0, 0.64)]
    assert rows(con, "SELECT count(*) FROM nba.team_games") == [(10,)]


def test_games_gates_pass_on_consistent_sources_and_flag_each_violation(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con, "sdv.nba_stats_schedules", [schedule("0020000500", "2001-01-05", BOS, LAL, (101, 99))]
    )
    insert(
        con,
        "sdv.nba_stats_team_boxscores",
        [
            {"game_id": "0020000500", "team_id": BOS, "points": 101},
            {"game_id": "0020000500", "team_id": LAL, "points": 99},
        ],
    )
    insert(
        con,
        "sdv.nba_schedule_crosswalk",
        [{"nba_game_id": "0020000500", "espn_game_id": "210105002"}],
    )
    insert(
        con,
        "sdv.espn_nba_schedule_master",
        [espn(210105002, "2001-01-06T00:30Z", BOS, LAL, (101, 99))],
    )
    build_models(con, *MODELS)
    names = (
        "games_game_id_unique",
        "games_home_and_away_differ",
        "games_competitive_teams_have_a_season",
        "games_team_games_two_per_game",
        "games_scores_agree_with_team_box",
        "games_espn_score_mismatches_under_0_1_percent",
        "games_fte_unmatched_under_0_1_percent",
    )
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)

    con.execute("UPDATE sdv.espn_nba_schedule_master SET home_score = 100")
    con.execute("UPDATE sdv.nba_stats_team_boxscores SET points = 102 WHERE team_id = ?", [BOS])
    insert(
        con,
        "sdv.nba_stats_schedules",
        [schedule("0020000501", "2001-01-06", BOS, 1610616857, (90, 80))],
    )
    build_models(con, *MODELS)

    assert check(con, gate("games_espn_score_mismatches_under_0_1_percent")).sample == [
        {"mismatched": 1, "matched": 1}
    ]
    assert check(con, gate("games_scores_agree_with_team_box")).sample[0]["home_box_pts"] == 102
    assert check(con, gate("games_competitive_teams_have_a_season")).sample == [
        {"game_id": "0020000501", "season": 2001, "team_id": 1610616857}
    ]


def test_games_and_team_games_carry_the_names_the_teams_used_that_season(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "bref.team_summaries",
        [
            {"season": 1950, "lg": "NBA", "team": "Minneapolis Lakers", "abbreviation": "MNL"},
            {"season": 1950, "lg": "NBA", "team": "New York Knicks", "abbreviation": "NYK"},
        ],
    )
    insert(
        con,
        "fte.elo",
        [
            elo("194911010MNL", "1949-11-01", 1950, "MNL", "NYK", 80, 70),
            elo("194911010MNL", "1949-11-01", 1950, "NYK", "MNL", 70, 80, copy=1, location="A"),
        ],
    )

    build_models(con, *MODELS)

    assert rows(con, "SELECT home_team_id, home_team_name, away_team_name FROM nba.games") == [
        (LAL, "Minneapolis Lakers", "New York Knicks")
    ]
    assert rows(
        con, "SELECT team_name, opponent_name FROM nba.team_games ORDER BY is_home DESC"
    ) == [("Minneapolis Lakers", "New York Knicks"), ("New York Knicks", "Minneapolis Lakers")]


def reference_elo(
    seed: dict[int, float], first_season: int, games: list[tuple], edges: dict[int, float]
) -> dict[tuple[str, int], tuple[float, float, float]]:
    ratings: dict[int, float] = {}
    season = first_season - 1
    out: dict[tuple[str, int], tuple[float, float, float]] = {}
    for game_id, game_season, home, away, home_pts, away_pts, neutral in games:
        if game_season > season:
            ratings = {
                t: 0.75 * ratings.get(t, seed.get(t, 1300.0)) + 0.25 * 1505 for t in (BOS, LAL, CHI)
            }
            season = game_season
        edge = 0 if neutral else edges.get(game_season, 100.0)
        for team, opp, margin, team_edge in (
            (home, away, home_pts - away_pts, edge),
            (away, home, away_pts - home_pts, -edge),
        ):
            diff = ratings[team] - ratings[opp] + team_edge
            p = 1 / (1 + 10 ** (-diff / 400))
            k = 20 * (abs(margin) + 3) ** 0.8 / (7.5 + 0.006 * (diff if margin > 0 else -diff))
            out[(game_id, team)] = (ratings[team], ratings[team] + k * ((margin > 0) - p), p)
        ratings[home], ratings[away] = out[(game_id, home)][1], out[(game_id, away)][1]
    return out


def test_team_elo_continues_fte_ratings_with_their_method_and_team_games_prefers_fte(
    con: duckdb.DuckDBPyConnection,
) -> None:
    seed = {BOS: 1600.0, LAL: 1450.0}
    games = [
        ("0020000001", 2001, BOS, LAL, 100, 90, False),
        ("0020000002", 2001, CHI, BOS, 95, 99, False),
        ("0040000001", 2001, LAL, CHI, 110, 100, False),
        ("0020100001", 2002, LAL, BOS, 88, 92, False),
        ("0020100002", 2002, BOS, CHI, 101, 102, True),
    ]
    dates = ["2000-11-01", "2000-11-03", "2001-05-01", "2001-11-01", "2001-11-05"]
    want = reference_elo(seed, 2001, games, {})
    want_fit = reference_elo(seed, 2001, games, {2002: 400 * math.log10(2)})
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            schedule(g, d, h, a, (hp, ap), season=s, season_type=t)
            for (g, s, h, a, hp, ap, _), d, t in zip(
                games,
                dates,
                [
                    "regular-season",
                    "regular-season",
                    "playoffs",
                    "regular-season",
                    "regular-season",
                ],
                strict=True,
            )
        ]
        + [schedule("0010000001", "2000-10-20", BOS, LAL, (90, 80), season_type="preseason")],
    )
    insert(
        con,
        "sdv.nba_schedule_crosswalk",
        [{"nba_game_id": "0020100002", "espn_game_id": "211105002"}],
    )
    insert(
        con,
        "sdv.espn_nba_schedule_master",
        [
            espn(
                211105002, "2001-11-06T00:30Z", BOS, CHI, (101, 102), season=2002, neutral_site=True
            )
        ],
    )
    bos_pre, bos_post, bos_p = want[("0020000001", BOS)]
    lal_pre, lal_post, lal_p = want[("0020000001", LAL)]
    insert(
        con,
        "fte.elo",
        [
            elo(
                "200003010BOS", "2000-03-01", 2000, "BOS", "LAL", 90, 99, gameorder=1, elo_n=1580.0
            ),
            elo(
                "200004010BOS", "2000-04-01", 2000, "BOS", "LAL", 99, 90, gameorder=2, elo_n=1600.0
            ),
            elo(
                "200004010BOS",
                "2000-04-01",
                2000,
                "LAL",
                "BOS",
                90,
                99,
                copy=1,
                location="A",
                gameorder=2,
                elo_n=1450.0,
            ),
            elo(
                "200011010BOS",
                "2000-11-01",
                2001,
                "BOS",
                "LAL",
                100,
                90,
                gameorder=3,
                elo_i=bos_pre,
                elo_n=bos_post,
                forecast=bos_p,
            ),
            elo(
                "200011010BOS",
                "2000-11-01",
                2001,
                "LAL",
                "BOS",
                90,
                100,
                copy=1,
                location="A",
                gameorder=3,
                elo_i=lal_pre,
                elo_n=lal_post,
                forecast=lal_p,
            ),
        ],
    )

    build_models(
        con, "arenas", "franchises", "team_seasons", "teams", "games", "team_elo", "team_games"
    )

    for columns, expected in (
        ("elo_pre, elo_post, win_prob", want),
        ("fit_pre, fit_post, fit_win_prob", want_fit),
    ):
        got = {
            (g, t): (pre, post, p)
            for g, t, pre, post, p in rows(
                con, f"SELECT game_id, team_id, {columns} FROM nba.team_elo"
            )
        }
        assert got.keys() == expected.keys()
        for key, values in expected.items():
            assert got[key] == pytest.approx(values, abs=1e-9)
    assert want_fit[("0020100001", LAL)] != pytest.approx(want[("0020100001", LAL)])
    assert rows(
        con,
        "SELECT game_id, elo_source FROM nba.team_games WHERE team_id = ? ORDER BY game_date",
        [BOS],
    ) == [
        ("0010000001", None),
        ("0020000001", "fte"),
        ("0020000002", "lake"),
        ("0020100001", "lake"),
        ("0020100002", "lake"),
    ]
    names = (
        "games_team_elo_key_unique",
        "games_team_elo_zero_sum_per_game",
        "games_team_elo_matches_fte_within_2_points",
        "games_competitive_games_have_elo",
    )
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)

    con.execute("UPDATE fte.elo SET elo_i = elo_i + 5 WHERE year_id = 2001 AND team_id = 'BOS'")
    assert check(con, gate("games_team_elo_matches_fte_within_2_points")).violations == 1


def test_bubble_games_are_neutral_site(con: duckdb.DuckDBPyConnection) -> None:
    insert(
        con,
        "sdv.nba_stats_schedules",
        [schedule("0021901000", "2020-07-30", BOS, LAL, (100, 90), season=2020)],
    )
    insert(
        con,
        "sdv.nba_schedule_crosswalk",
        [{"nba_game_id": "0021901000", "espn_game_id": "401220000"}],
    )
    insert(
        con,
        "sdv.espn_nba_schedule_master",
        [
            espn(
                401220000,
                "2020-07-30T22:30Z",
                BOS,
                LAL,
                (100, 90),
                season=2020,
                venue_full_name="ESPN Wide World of Sports Complex",
            )
        ],
    )
    build_models(con, "franchises", "team_seasons", "teams", "games")
    assert game(con, "0021901000", "neutral_site", "venue") == (
        True,
        "ESPN Wide World of Sports Complex",
    )


def arena_km(a: str, b: str, team_ids: tuple[int | None, int | None] = (None, None)) -> float:
    seed = Path(__file__).parents[1] / "src/nbalake/sql/seed/arenas.csv"
    coords = {
        (r["arena"], int(r["team_id"]) if r["team_id"] else None): (
            float(r["latitude"]),
            float(r["longitude"]),
        )
        for r in csv.DictReader(seed.open())
    }
    (la1, lo1), (la2, lo2) = coords[(a, team_ids[0])], coords[(b, team_ids[1])]
    h = (
        math.sin(math.radians(la2 - la1) / 2) ** 2
        + math.cos(math.radians(la1))
        * math.cos(math.radians(la2))
        * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def test_travel_runs_from_the_previous_competitive_game_location_to_this_one(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "bref.team_summaries",
        [
            {"season": 2001, "lg": "NBA", "team": t, "abbreviation": a, "arena": arena}
            for t, a, arena in (
                ("Boston Celtics", "BOS", "FleetCenter"),
                ("Los Angeles Lakers", "LAL", "STAPLES Center"),
                ("Chicago Bulls", "CHI", "United Center"),
            )
        ]
        + [
            {
                "season": 1975,
                "lg": "NBA",
                "team": t,
                "abbreviation": a,
                "arena": "Municipal Auditorium",
            }
            for t, a in (("Kansas City-Omaha Kings", "KCO"), ("New Orleans Jazz", "NOJ"))
        ],
    )
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            schedule("0010000001", "2000-10-20", CHI, BOS, (90, 80), season_type="preseason"),
            schedule("0020000001", "2000-11-01", BOS, LAL, (100, 90)),
            schedule("0020000002", "2000-11-03", CHI, BOS, (95, 99)),
            schedule("0020000003", "2000-11-05", BOS, CHI, (101, 102)),
            schedule("0020000004", "2000-11-07", BOS, LAL, (99, 98)),
            schedule("0020000005", "2000-11-10", LAL, BOS, (88, 92)),
        ],
    )
    insert(
        con,
        "sdv.nba_schedule_crosswalk",
        [{"nba_game_id": "0020000005", "espn_game_id": "201110013"}],
    )
    insert(
        con,
        "sdv.espn_nba_schedule_master",
        [
            espn(
                201110013,
                "2000-11-11T01:00Z",
                LAL,
                BOS,
                (88, 92),
                neutral_site=True,
                venue_full_name="Mexico City Arena",
            )
        ],
    )
    insert(
        con,
        "fte.elo",
        [
            elo("197411010KCO", "1974-11-01", 1975, "KCO", "NOJ", 100, 90),
            elo("197411010KCO", "1974-11-01", 1975, "NOJ", "KCO", 90, 100, copy=1, location="A"),
            elo("197411030NOJ", "1974-11-03", 1975, "NOJ", "KCO", 100, 90),
            elo("197411030NOJ", "1974-11-03", 1975, "KCO", "NOJ", 90, 100, copy=1, location="A"),
        ],
    )

    build_models(con, *MODELS)

    got = rows(
        con,
        "SELECT game_id, travel_km FROM nba.team_games WHERE team_id = ? ORDER BY game_date",
        [BOS],
    )
    want = [
        ("0010000001", None),
        ("0020000001", None),
        ("0020000002", arena_km("FleetCenter", "United Center")),
        ("0020000003", arena_km("United Center", "FleetCenter")),
        ("0020000004", 0.0),
        ("0020000005", arena_km("FleetCenter", "Mexico City Arena")),
    ]
    assert [g for g, _ in got] == [g for g, _ in want]
    assert [km for _, km in got] == pytest.approx([km for _, km in want], abs=1e-6)
    assert 1300 < want[2][1] < 1450
    kings = 1610612758
    assert rows(
        con,
        "SELECT travel_km FROM nba.team_games WHERE team_id = ? AND season = 1975 "
        "ORDER BY game_date",
        [kings],
    ) == [
        (None,),
        (
            pytest.approx(
                arena_km("Municipal Auditorium", "Municipal Auditorium", (kings, 1610612762))
            ),
        ),
    ]
    names = (
        "games_arenas_key_unique",
        "games_travel_km_within_half_the_earth",
        "games_competitive_games_located_over_99_percent",
    )
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)

    con.execute("UPDATE bref.team_summaries SET arena = 'Nowhere Arena' WHERE abbreviation = 'CHI'")
    build_models(con, *MODELS)
    assert check(con, gate("games_competitive_games_located_over_99_percent")).violations == 1


ESPN_GATES = (
    "games_game_xref_key_unique",
    "games_espn_sourced_games_have_no_other_row",
    "games_completed_espn_games_after_nba_stats_have_a_row",
)


def test_completed_espn_games_after_the_last_nba_stats_game_are_minted_until_nba_stats_has_them(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con, "sdv.nba_stats_schedules", [schedule("0020000500", "2001-01-05", BOS, LAL, (101, 99))]
    )
    insert(
        con,
        "sdv.espn_nba_schedule_master",
        [
            espn(210103004, "2001-01-03T00:30Z", CHI, BOS, (90, 91)),
            espn(210105002, "2001-01-06T00:30Z", BOS, LAL, (101, 99)),
            espn(
                210110002, "2001-01-11T00:30Z", BOS, CHI, (100, 90), venue_full_name="FleetCenter"
            ),
            espn(210112013, "2001-01-13T03:30Z", LAL, BOS, (0, 0), status_type_completed=False),
        ],
    )
    build_models(con, *MODELS, "game_xref")

    assert rows(
        con,
        "SELECT game_id, season, season_type, game_date, home_pts, away_pts, venue, espn_game_id, "
        "source FROM nba.games WHERE source = 'espn'",
    ) == [
        (
            "espn210110002",
            2001,
            "regular",
            date(2001, 1, 10),
            100,
            90,
            "FleetCenter",
            210110002,
            "espn",
        )
    ]
    assert rows(
        con, "SELECT team_id, won FROM nba.team_games WHERE game_id = 'espn210110002' ORDER BY 1"
    ) == [(BOS, True), (CHI, False)]
    assert {n: check(con, gate(n)).violations for n in ESPN_GATES} == dict.fromkeys(ESPN_GATES, 0)

    insert(
        con,
        "sdv.nba_stats_schedules",
        [schedule("0020000600", "2001-01-10", BOS, CHI, (100, 90))],
    )
    build_models(con, *MODELS, "game_xref")

    assert rows(con, "SELECT game_id FROM nba.games WHERE source = 'espn'") == []
    assert rows(
        con,
        "SELECT source, game_id FROM nba.game_xref "
        "WHERE source_id IN ('espn210110002', '210110002') ORDER BY 1",
    ) == [("espn", "0020000600"), ("minted", "0020000600")]
    assert {n: check(con, gate(n)).violations for n in ESPN_GATES} == dict.fromkeys(ESPN_GATES, 0)


def test_espn_sourced_gates_flag_a_duplicate_and_a_dropped_espn_game(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con, "sdv.nba_stats_schedules", [schedule("0020000500", "2001-01-05", BOS, LAL, (101, 99))]
    )
    insert(
        con,
        "sdv.espn_nba_schedule_master",
        [
            espn(210110002, "2001-01-11T00:30Z", BOS, CHI, (100, 90)),
            espn(210111002, "2001-01-12T00:30Z", BOS, CHI, (100, 90)),
        ],
    )
    build_models(con, *MODELS)
    con.execute("UPDATE nba.games SET game_date = '2001-01-10' WHERE game_id = 'espn210111002'")
    con.execute("DELETE FROM nba.games WHERE game_id = 'espn210110002'")
    insert(
        con,
        "sdv.nba_stats_schedules",
        [schedule("0020000600", "2001-01-10", BOS, CHI, (100, 90))],
    )
    con.execute(
        "INSERT INTO nba.games (game_id, season, game_date, home_team_id, away_team_id, source) "
        "VALUES ('0020000600', 2001, '2001-01-10', ?, ?, 'nba')",
        [BOS, CHI],
    )

    assert check(con, gate("games_espn_sourced_games_have_no_other_row")).sample == [
        {"game_id": "espn210111002", "other_game_id": "0020000600"}
    ]
    assert check(con, gate("games_completed_espn_games_after_nba_stats_have_a_row")).violations == 0
    con.execute("DELETE FROM nba.games WHERE game_id = '0020000600'")
    con.execute("DELETE FROM sdv.nba_stats_schedules WHERE game_id = '0020000600'")
    assert [
        r["espn_game_id"]
        for r in check(con, gate("games_completed_espn_games_after_nba_stats_have_a_row")).sample
    ] == [210110002]


def test_a_postponed_game_takes_the_rescheduled_espn_id_over_the_crosswalks_postponed_one(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con, "sdv.nba_stats_schedules", [schedule("0020000529", "2001-01-29", CHI, LAL, (113, 116))]
    )
    insert(
        con,
        "sdv.nba_schedule_crosswalk",
        [{"nba_game_id": "0020000529", "espn_game_id": "210108004"}],
    )
    insert(
        con,
        "sdv.espn_nba_schedule_master",
        [
            espn(210108004, "2001-01-09T01:00Z", CHI, LAL, (0, 0), status_type_completed=False),
            espn(210129004, "2001-01-30T01:00Z", CHI, LAL, (113, 116)),
        ],
    )
    build_models(con, *MODELS)

    assert game(con, "0020000529", "espn_game_id") == (210129004,)


def test_all_star_games_match_espn_on_the_date_and_the_score(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            schedule(
                "0030000001",
                "2001-02-11",
                1610616833,
                1610616834,
                (111, 110),
                season_type="all-star",
            ),
            schedule(
                "0030000002", "2001-02-11", 1610616835, 1610616833, (42, 40), season_type="all-star"
            ),
        ],
    )
    insert(
        con,
        "sdv.espn_nba_schedule_master",
        [
            {
                **espn(210211031, "2001-02-11T22:00Z", BOS, LAL, (111, 110)),
                "home_id": 31,
                "away_id": 32,
                "type_abbreviation": "ALLSTAR",
            },
            {
                **espn(210211032, "2001-02-11T23:00Z", BOS, LAL, (42, 40)),
                "home_id": 33,
                "away_id": 31,
                "type_abbreviation": "ALLSTAR",
            },
        ],
    )
    build_models(con, *MODELS)

    assert rows(con, "SELECT game_id, espn_game_id FROM nba.games ORDER BY 1") == [
        ("0030000001", 210211031),
        ("0030000002", 210211032),
    ]


def test_a_competitive_game_scored_zero_to_zero_was_never_played_and_is_not_published(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            schedule("0020000900", "2001-01-05", BOS, LAL, (101, 99)),
            schedule("0020000901", "2001-01-06", LAL, BOS, (0, 0)),
            schedule("0010000900", "2000-10-05", BOS, LAL, (0, 0), season_type="preseason"),
        ],
    )

    build_models(con, *MODELS)

    assert rows(con, "SELECT game_id FROM nba.games ORDER BY game_id") == [
        ("0010000900",),
        ("0020000900",),
    ]
    assert rows(con, "SELECT DISTINCT game_id FROM nba.team_games ORDER BY game_id") == [
        ("0010000900",),
        ("0020000900",),
    ]
    assert check(con, gate("games_competitive_games_have_points")).violations == 0

    con.execute("UPDATE nba.games SET home_pts = 0, away_pts = 0 WHERE game_id = '0020000900'")
    assert check(con, gate("games_competitive_games_have_points")).sample == [
        {"game_id": "0020000900", "season": 2001}
    ]


def test_a_neutral_site_fte_row_listing_the_away_team_first_matches_and_swaps_its_score(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con, "sdv.nba_stats_schedules", [schedule("0020100100", "2001-11-08", BOS, LAL, (101, 99))]
    )
    insert(
        con,
        "fte.elo",
        [
            elo(
                "200111080BOS", "2001-11-08", 2001, "LAL", "BOS", 99, 101, location="N", elo_i=1500
            ),
            elo(
                "200111080BOS",
                "2001-11-08",
                2001,
                "BOS",
                "LAL",
                101,
                99,
                copy=1,
                location="N",
                elo_i=1510,
            ),
        ],
    )

    build_models(con, *MODELS)

    assert game(con, "0020100100", "fte_game_id", "neutral_site") == ("200111080BOS", True)
    assert rows(
        con, "SELECT team_id, elo_pre, elo_source FROM nba.team_games ORDER BY team_id"
    ) == [(BOS, 1510, "fte"), (LAL, 1500, "fte")]
    assert rows(con, "SELECT count(*) FROM nba.games_cross_source") == [(0,)]
    assert check(con, gate("games_competitive_games_have_elo")).violations == 0


def test_a_game_fte_dates_differently_matches_on_teams_and_score_when_unique(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con, "sdv.nba_stats_schedules", [schedule("0020000500", "2001-01-05", BOS, LAL, (101, 99))]
    )
    insert(
        con,
        "fte.elo",
        [
            elo("200101040BOS", "2001-01-04", 2001, "BOS", "LAL", 101, 99, elo_i=1500),
            elo("200101040BOS", "2001-01-04", 2001, "LAL", "BOS", 99, 101, copy=1, elo_i=1490),
        ],
    )

    build_models(con, *MODELS)

    assert game(con, "0020000500", "fte_game_id") == ("200101040BOS",)
    assert check(con, gate("games_competitive_games_have_elo")).violations == 0


def test_games_fte_dates_differently_do_not_match_when_the_score_is_not_unique(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            schedule("0020000500", "2001-01-05", BOS, LAL, (100, 90)),
            schedule("0020000600", "2001-02-05", BOS, LAL, (100, 90)),
        ],
    )
    insert(
        con,
        "fte.elo",
        [
            elo("200101040BOS", "2001-01-04", 2001, "BOS", "LAL", 100, 90, elo_i=1500),
            elo("200102040BOS", "2001-02-04", 2001, "BOS", "LAL", 100, 90, elo_i=1500),
        ],
    )

    build_models(con, *MODELS)

    assert rows(con, "SELECT game_id, fte_game_id FROM nba.games ORDER BY game_id") == [
        ("0020000500", None),
        ("0020000600", None),
    ]
