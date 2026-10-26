from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import duckdb
import pytest

from nbalake.curate import check
from nbalake.lake import Root
from tests.curated import build_models, empty_lake, gate, insert, rows, sources

MODELS = ("franchises", "team_seasons", "games", "odds_teams", "game_lines")
DEN, MIA = 1610612743, 1610612748
OPENER = dt.date(2015, 11, 1)


def game_id(n: int) -> str:
    return f"00215{n:05d}"


def schedule(n: int, home_pts: int = 100, away_pts: int = 98) -> dict:
    return {
        "game_id": game_id(n),
        "season": 2016,
        "season_type": "regular-season",
        "game_date": OPENER + dt.timedelta(days=n),
        "home_team_id": DEN,
        "home_team_abbreviation": "DEN",
        "away_team_id": MIA,
        "away_team_abbreviation": "MIA",
        "home_pts": home_pts,
        "away_pts": away_pts,
    }


def line(n: int, favored: str = "home", spread: float = 4.5, **extra: object) -> dict:
    return {
        "season": 2016,
        "date": OPENER + dt.timedelta(days=n),
        "home": "den",
        "away": "mia",
        "whos_favored": favored,
        "spread": spread,
        "total": 201.5,
        "moneyline_home": -180,
        "moneyline_away": 155,
        **extra,
    }


def book_row(n: int, book: str = "Pinnacle Sports", away: int = MIA, home: int = DEN) -> dict:
    return {
        "game_id": game_id(n),
        "book_name": book,
        "book_id": "238",
        "team_id": str(away),
        "a_team_id": str(home),
    }


def espn_play(n: int, home_team_spread: float, available: bool = True) -> dict:
    return {
        "game_id": 400000000 + n,
        "season": 2016,
        "home_team_spread": home_team_spread,
        "game_spread_available": available,
    }


def crosswalk(n: int) -> dict:
    return {"nba_game_id": game_id(n), "espn_game_id": str(400000000 + n)}


def lines(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    return rows(
        con,
        "SELECT game_id, source, book, home_spread, home_spread_price, away_spread_price, total, "
        "home_moneyline, away_moneyline FROM nba.game_lines ORDER BY game_id, source, book",
    )


@pytest.fixture
def con(root: Root) -> Iterator[duckdb.DuckDBPyConnection]:
    con = empty_lake(root, sources(*MODELS, gate_prefix="odds_"))
    insert(con, "sdv.nba_stats_schedules", [schedule(n) for n in range(1, 11)])
    yield con
    con.close()


def test_kaggle_lines_sign_the_spread_by_the_favored_side_and_join_games_by_date_and_teams(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(con, "odds.lines", [line(1), line(2, favored="away", spread=3.0)])
    build_models(con, *MODELS)

    assert lines(con) == [
        (game_id(1), "kaggle_lines", None, -4.5, None, None, 201.5, -180, 155),
        (game_id(2), "kaggle_lines", None, 3.0, None, None, 201.5, -180, 155),
    ]
    names = (
        "odds_game_lines_key_unique",
        "odds_every_line_code_maps",
        "odds_lines_match_games_under_0_1_percent",
    )
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)


def test_a_line_with_an_unmapped_team_code_is_dropped_and_fails_the_code_and_match_gates(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(con, "odds.lines", [line(1), line(2, away="sea")])
    build_models(con, *MODELS)

    assert [r[0] for r in lines(con)] == [game_id(1)]
    assert check(con, gate("odds_every_line_code_maps")).sample == [{"code": "sea"}]
    assert check(con, gate("odds_lines_match_games_under_0_1_percent")).sample == [
        {"unmatched": 1, "total": 2}
    ]


def test_book_markets_merge_per_game_and_book_with_home_taken_from_the_second_column(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "odds.book_spreads",
        [{**book_row(1), "spread1": "4.5", "spread2": "-4.5", "price1": "-104", "price2": "-106"}],
    )
    insert(
        con,
        "odds.book_totals",
        [{**book_row(1), "total1": "201.5", "total2": "201.5", "price1": "-110", "price2": "-110"}],
    )
    insert(
        con,
        "odds.book_moneylines",
        [
            {**book_row(1), "price1": "160", "price2": "-185"},
            {**book_row(1, book="5Dimes"), "price1": "150", "price2": "-170"},
        ],
    )
    build_models(con, *MODELS)

    assert lines(con) == [
        (game_id(1), "kaggle_books", "5Dimes", None, None, None, None, -170, 150),
        (game_id(1), "kaggle_books", "Pinnacle Sports", -4.5, -106, -104, 201.5, -185, 160),
    ]
    names = ("odds_every_book_row_matches_a_game", "odds_book_teams_agree_with_games")
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)


def test_book_rows_whose_away_team_is_not_the_games_away_team_fail_the_orientation_gate(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "odds.book_moneylines",
        [{**book_row(1, away=DEN, home=MIA), "price1": "-185", "price2": "160"}],
    )
    build_models(con, *MODELS)

    flagged = check(con, gate("odds_book_teams_agree_with_games"))
    assert [(r["game_id"], r["team_id"], r["away_team_id"]) for r in flagged.sample] == [
        (game_id(1), str(DEN), MIA)
    ]


def test_espn_spreads_flip_to_home_points_and_skip_games_without_an_available_line(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(con, "sdv.nba_schedule_crosswalk", [crosswalk(1), crosswalk(2)])
    insert(
        con,
        "sdv.espn_nba_pbp",
        [espn_play(1, 6.5), espn_play(1, 6.5), espn_play(2, 2.5, available=False)],
    )
    build_models(con, *MODELS)

    assert lines(con) == [(game_id(1), "espn", None, -6.5, None, None, None, None, None)]


def test_a_flipped_spread_sign_fails_the_favorite_win_rate_gate(
    con: duckdb.DuckDBPyConnection,
) -> None:
    home_wins = [line(n) for n in range(1, 8)]
    home_losses = [line(n) for n in range(8, 11)]
    con.execute("UPDATE sdv.nba_stats_schedules SET home_pts = 90 WHERE game_id >= ?", [game_id(8)])
    insert(con, "odds.lines", home_wins + home_losses)
    build_models(con, *MODELS)
    assert check(con, gate("odds_favorites_win_60_to_75_percent")).violations == 0

    con.execute("DELETE FROM odds.lines")
    insert(con, "odds.lines", [line(n, favored="away") for n in range(1, 11)])
    build_models(con, *MODELS)

    flagged = check(con, gate("odds_favorites_win_60_to_75_percent"))
    assert [(r["source"], r["games"], r["favorite_win_rate"]) for r in flagged.sample] == [
        ("kaggle_lines", 10, 0.3)
    ]


def test_kaggle_lines_more_than_a_point_from_espn_fail_the_agreement_gate(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(con, "sdv.nba_schedule_crosswalk", [crosswalk(1), crosswalk(2)])
    insert(con, "sdv.espn_nba_pbp", [espn_play(1, 4.5), espn_play(2, 3.5)])
    insert(con, "odds.lines", [line(1, spread=5.5), line(2, spread=1.0)])
    build_models(con, *MODELS)

    assert check(con, gate("odds_lines_agree_with_espn_within_a_point_over_90_percent")).sample == [
        {"games": 2, "within_a_point": 0.5}
    ]


def test_totals_outside_150_to_300_fail_the_range_gate_past_its_threshold(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(con, "odds.lines", [line(n) for n in range(1, 11)])
    build_models(con, *MODELS)
    assert check(con, gate("odds_totals_in_range_under_0_2_percent")).violations == 0

    insert(con, "odds.book_totals", [{**book_row(1), "total1": "2.5", "total2": "2.5"}])
    build_models(con, *MODELS)

    assert check(con, gate("odds_totals_in_range_under_0_2_percent")).sample == [
        {"out_of_range": 1, "totals": 11}
    ]
