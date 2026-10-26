from __future__ import annotations

import duckdb
import pytest

from tests.test_metric_career_postseason import A, B, Game, Playoffs, lake, rows


def weights(con: duckdb.DuckDBPyConnection, sql: str) -> dict[tuple[int, int], float]:
    return {(r["season"], r["round"]): r["round_weight"] for r in rows(con, sql)}


def test_a_run_splits_by_positive_win_shares_and_sums_to_five_times_the_runs_team_credit() -> None:
    games = [
        Game("g1", A, B, True, season=1965, day="1965-04-01"),
        Game("g2", A, B, False, season=1965, day="1965-04-03"),
    ]
    win_shares = [(1965, A, 11, 9.0), (1965, A, 12, 3.0), (1965, A, 13, -1.5), (1965, B, 21, 5.0)]
    con = lake(Playoffs({A: 1600, B: 1500}, games, win_shares=win_shares))

    run = rows(
        con,
        "SELECT sum(team_credit) AS t FROM postseason_team_credit("
        "rounds := 'from_final', first_season := 1958) WHERE team_id = 1",
    )[0]["t"]
    found = rows(con, "FROM postseason_basic_season_credit() WHERE team_id = 1")

    assert {r["player_id"]: r["share"] for r in found} == pytest.approx(
        {11: 0.75, 12: 0.25, 13: 0.0}
    )
    assert {r["games"] for r in found} == {2}
    assert sum(r["credit"] for r in found) == pytest.approx(5 * run)


def test_from_final_weighs_a_three_round_finals_like_a_four_round_one() -> None:
    games = [
        Game("r1", A, B, True, round=1, season=1965, day="1965-03-20"),
        Game("r2", A, B, True, round=2, season=1965, day="1965-04-01"),
        Game("r3", A, B, True, round=3, season=1965, day="1965-04-20"),
        Game("f4", A, B, True, round=4, season=1985, day="1985-06-01"),
        Game("f3", A, B, True, round=3, season=1985, day="1985-05-20"),
    ]
    con = lake(Playoffs({A: 1600, B: 1500}, games))

    found = weights(
        con,
        "SELECT DISTINCT season, round, round_weight FROM postseason_team_credit("
        "rounds := 'from_final', first_season := 1958)",
    )

    assert found == {(1965, 1): 2, (1965, 2): 3, (1965, 3): 4, (1985, 3): 3, (1985, 4): 4}


def test_from_final_in_playoffs_in_progress_assumes_last_seasons_round_count() -> None:
    games = [
        Game("done", A, B, True, round=4, season=1995, day="1995-06-01"),
        Game("now", A, B, True, round=1, season=1996, day="1996-04-20"),
    ]
    con = lake(Playoffs({A: 1600, B: 1500}, games))

    found = weights(
        con,
        "SELECT DISTINCT season, round, round_weight FROM postseason_team_credit("
        "rounds := 'from_final')",
    )

    assert found == {(1995, 4): 4, (1996, 1): 1}


def test_runs_before_1958_count_nothing_unless_first_season_says_so() -> None:
    games = [
        Game("old", A, B, True, season=1957, day="1957-04-01"),
        Game("new", A, B, True, season=1958, day="1958-04-01"),
    ]
    win_shares = [(s, t, t * 10, 4.0) for s in (1957, 1958) for t in (A, B)]
    con = lake(Playoffs({A: 1600, B: 1500}, games, win_shares=win_shares))

    default = rows(con, "SELECT DISTINCT season FROM postseason_basic_season_credit()")
    earlier = rows(
        con,
        "SELECT DISTINCT season FROM postseason_basic_season_credit("
        "first_season := 1957) ORDER BY season",
    )

    assert default == [{"season": 1958}]
    assert earlier == [{"season": 1957}, {"season": 1958}]


def test_career_basic_sums_each_players_runs_ranked_by_credit() -> None:
    games = [
        Game("a", A, B, True, season=1965, day="1965-04-01"),
        Game("b", A, B, True, season=1966, day="1966-04-01"),
    ]
    win_shares = [(s, t, t * 10, 4.0) for s in (1965, 1966) for t in (A, B)]
    con = lake(Playoffs({A: 1600, B: 1500}, games, win_shares=win_shares))
    con.execute("INSERT INTO nba.players VALUES (10, 'Ace'), (20, 'Bee')")

    runs = rows(con, "SELECT player_id, credit FROM postseason_basic_season_credit()")
    career = rows(con, "FROM career_postseason_basic()")

    assert [(r["rank"], r["player"], r["runs"]) for r in career] == [(1, "Ace", 2), (2, "Bee", 2)]
    assert career[0]["credit"] == pytest.approx(
        sum(r["credit"] for r in runs if r["player_id"] == 10)
    )
