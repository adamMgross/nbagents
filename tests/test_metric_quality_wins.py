from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import duckdb
import pytest

from nbalake.explore import macros

A, B, C, D = 1, 2, 3, 4
NEEDS = {
    "elo_game_prob",
    "quality_win_team_game",
    "quality_win_team_season",
    "quality_win_game",
    "quality_win_season",
    "career_quality_wins",
}


@dataclass(frozen=True, slots=True)
class Game:
    game_id: str
    home: int
    away: int
    home_won: bool
    season: int = 2000
    neutral: bool = False


@dataclass
class Season:
    elo: dict[int, float | None]
    games: list[Game]
    box: list[tuple[str, int, int, int]] = field(default_factory=list)
    win_shares: list[tuple[int, int, int, float, int | None]] = field(default_factory=list)


def lake(s: Season) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("CREATE SCHEMA nba")
    con.execute(
        "CREATE TABLE nba.games (game_id VARCHAR, season INTEGER, season_type VARCHAR, "
        "lg VARCHAR, neutral_site BOOLEAN, home_team_id BIGINT)"
    )
    con.execute(
        "CREATE TABLE nba.team_games (game_id VARCHAR, game_date DATE, team_id BIGINT, "
        "opponent_team_id BIGINT, won BOOLEAN, is_home BOOLEAN, elo_pre DOUBLE, elo_fit_pre DOUBLE)"
    )
    con.execute("CREATE TABLE nba.team_elo (game_id VARCHAR, team_id BIGINT, fit_edge DOUBLE)")
    con.execute(
        "CREATE TABLE nba.player_box (game_id VARCHAR, season INTEGER, team_id BIGINT, "
        "player_id HUGEINT, seconds INTEGER, played BOOLEAN)"
    )
    con.execute(
        "CREATE TABLE nba.player_seasons (season INTEGER, lg VARCHAR, team_id BIGINT, "
        "player_id HUGEINT, ws DOUBLE, mp BIGINT)"
    )
    con.execute("CREATE TABLE nba.players (player_id HUGEINT, name VARCHAR)")
    con.execute("CREATE TABLE nba.team_seasons (season INTEGER, team_id BIGINT, name VARCHAR)")
    for g in s.games:
        con.execute(
            "INSERT INTO nba.games VALUES (?, ?, 'regular', 'NBA', ?, ?)",
            [g.game_id, g.season, g.neutral, g.home],
        )
        for team, opp, home, won in (
            (g.home, g.away, True, g.home_won),
            (g.away, g.home, False, not g.home_won),
        ):
            con.execute(
                "INSERT INTO nba.team_games VALUES (?, '2000-01-01', ?, ?, ?, ?, ?, NULL)",
                [g.game_id, team, opp, won, home, s.elo[team]],
            )
    for game_id, team, player, seconds in s.box:
        season = next(g.season for g in s.games if g.game_id == game_id)
        con.execute(
            "INSERT INTO nba.player_box VALUES (?, ?, ?, ?, ?, true)",
            [game_id, season, team, player, seconds],
        )
    for season, team, player, ws, mp in s.win_shares:
        con.execute(
            "INSERT INTO nba.player_seasons VALUES (?, 'NBA', ?, ?, ?, ?)",
            [season, team, player, ws, mp],
        )
    for m in macros.shipped():
        if m.name in NEEDS:
            con.execute(m.sql)
    return con


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cur = con.execute(sql)
    names = [d[0] for d in cur.description or ()]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]


def credit(con: duckdb.DuckDBPyConnection, game_id: str, team: int) -> float:
    found = rows(
        con,
        "SELECT credit FROM quality_win_team_game() "
        f"WHERE game_id = '{game_id}' AND team_id = {team}",
    )
    assert len(found) == 1
    return found[0]["credit"]


def even_box(*games: Game) -> list[tuple[str, int, int, int]]:
    return [(g.game_id, t, t * 10, 2880) for g in games for t in (g.home, g.away)]


def test_a_win_over_a_stronger_opponent_counts_more_than_one_over_a_weaker_one() -> None:
    games = [Game("strong", A, B, True), Game("weak", A, C, True)]
    con = lake(Season({A: 1500, B: 1650, C: 1350}, games))

    assert credit(con, "strong", A) > credit(con, "weak", A) > 0


def test_a_road_win_counts_more_than_the_same_win_at_home() -> None:
    games = [Game("home", A, B, True), Game("road", B, A, False)]
    con = lake(Season({A: 1500, B: 1500}, games))

    assert credit(con, "road", A) > credit(con, "home", A)


def test_a_loss_counts_zero_whoever_the_opponent() -> None:
    games = [Game("to_strong", B, A, True), Game("to_weak", C, A, True)]
    con = lake(Season({A: 1500, B: 1700, C: 1300}, games))

    assert credit(con, "to_strong", A) == 0
    assert credit(con, "to_weak", A) == 0


def test_a_seasons_quality_wins_add_up_to_its_wins() -> None:
    games = [
        Game("g1", A, B, True),
        Game("g2", C, A, True),
        Game("g3", B, D, False),
        Game("g4", D, C, True, neutral=True),
    ]
    con = lake(Season({A: 1600, B: 1450, C: 1550, D: 1400}, games))

    found = rows(
        con, "SELECT sum(quality_wins) AS q, sum(wins) AS w FROM quality_win_team_season()"
    )

    assert found[0]["q"] == pytest.approx(found[0]["w"])


def test_the_same_record_against_the_same_schedule_ranks_higher_for_beating_the_better_teams() -> (
    None
):
    games = [
        Game("a_beats_strong", A, C, True),
        Game("a_loses_to_weak", A, D, False),
        Game("b_beats_weak", B, D, True),
        Game("b_loses_to_strong", B, C, False),
    ]
    con = lake(Season({A: 1500, B: 1500, C: 1700, D: 1300}, games))

    found = {
        r["team_id"]: r
        for r in rows(
            con, "SELECT team_id, wins, quality_wins, rank FROM quality_win_team_season()"
        )
    }

    assert found[A]["wins"] == found[B]["wins"] == 1
    assert found[A]["quality_wins"] > found[B]["quality_wins"]
    assert found[A]["rank"] < found[B]["rank"]


def test_a_win_with_no_elo_counts_as_the_seasons_average_win() -> None:
    games = [Game("priced", A, B, True), Game("unpriced", C, D, True)]
    con = lake(Season({A: 1500, B: 1550, C: None, D: None}, games))

    assert credit(con, "unpriced", C) == 1


def test_a_games_credit_splits_by_seconds_times_win_shares_per_minute() -> None:
    g = Game("g1", A, B, True)
    con = lake(
        Season(
            {A: 1500, B: 1500},
            [g],
            box=[("g1", A, 11, 2400), ("g1", A, 12, 1200), ("g1", A, 13, 600), ("g1", B, 20, 2880)],
            win_shares=[
                (2000, A, 11, 10.0, 2000),
                (2000, A, 12, 2.0, 1000),
                (2000, A, 13, -1.0, 500),
            ],
        )
    )

    found = rows(
        con,
        "SELECT player_id, share, credit, team_credit FROM quality_win_game() WHERE team_id = 1",
    )

    share = {r["player_id"]: r["share"] for r in found}
    weights = {11: 2400 * 10 / 2000, 12: 1200 * 2 / 1000, 13: 0}
    assert share == pytest.approx({k: v / sum(weights.values()) for k, v in weights.items()})
    assert sum(r["credit"] for r in found) == pytest.approx(found[0]["team_credit"])


def test_minutes_shares_split_a_game_by_seconds_alone() -> None:
    g = Game("g1", A, B, True)
    con = lake(
        Season(
            {A: 1500, B: 1500},
            [g],
            box=[("g1", A, 11, 2160), ("g1", A, 12, 720), ("g1", B, 20, 2880)],
            win_shares=[(2000, A, 11, 1.0, 2000), (2000, A, 12, 9.0, 2000)],
        )
    )

    found = rows(
        con, "SELECT player_id, share FROM quality_win_game(shares := 'minutes') WHERE team_id = 1"
    )

    assert {r["player_id"]: r["share"] for r in found} == pytest.approx({11: 0.75, 12: 0.25})


def test_a_missed_game_gives_the_player_nothing_and_leaves_his_other_games_untouched() -> None:
    games = [Game("with", A, B, True), Game("without", A, C, True)]
    shares = [(2000, A, 11, 8.0, 2000), (2000, A, 12, 4.0, 2000)]
    played_both = lake(
        Season(
            {A: 1500, B: 1500, C: 1500},
            games,
            box=[
                ("with", A, 11, 1440),
                ("with", A, 12, 1440),
                ("without", A, 11, 1440),
                ("without", A, 12, 1440),
                *even_box(*games)[1::2],
            ],
            win_shares=shares,
        )
    )
    missed_one = lake(
        Season(
            {A: 1500, B: 1500, C: 1500},
            games,
            box=[
                ("with", A, 11, 1440),
                ("with", A, 12, 1440),
                ("without", A, 12, 1440),
                *even_box(*games)[1::2],
            ],
            win_shares=shares,
        )
    )
    query = "SELECT game_id, player_id, credit FROM quality_win_game() WHERE team_id = 1"

    before = {(r["game_id"], r["player_id"]): r["credit"] for r in rows(played_both, query)}
    after = {(r["game_id"], r["player_id"]): r["credit"] for r in rows(missed_one, query)}

    assert after[("with", 11)] == pytest.approx(before[("with", 11)])
    assert ("without", 11) not in after
    assert after[("without", 12)] == pytest.approx(credit(missed_one, "without", A))


def test_before_1994_the_seasons_win_shares_split_every_game() -> None:
    g = Game("old", A, B, True, season=1980)
    con = lake(
        Season(
            {A: 1500, B: 1500},
            [g],
            win_shares=[
                (1980, A, 11, 6.0, None),
                (1980, A, 12, 2.0, None),
                (1980, B, 20, 1.0, None),
            ],
        )
    )

    found = rows(
        con, "SELECT player_id, share, share_basis FROM quality_win_game() WHERE team_id = 1"
    )
    seasons = rows(con, "SELECT games, wins FROM quality_win_season() WHERE player_id = 11")

    assert {r["player_id"]: r["share"] for r in found} == pytest.approx({11: 0.75, 12: 0.25})
    assert {r["share_basis"] for r in found} == {"season totals"}
    assert seasons == [{"games": None, "wins": None}]


def test_a_career_sums_its_seasons_and_names_the_best_one() -> None:
    games = [Game("y1", A, B, True, season=2000), Game("y2", A, B, True, season=2001)]
    con = lake(
        Season(
            {A: 1500, B: 1500},
            games,
            box=[
                ("y1", A, 11, 2880),
                ("y2", A, 11, 1440),
                ("y2", A, 12, 1440),
                *even_box(*games)[1::2],
            ],
            win_shares=[
                (2000, A, 11, 5.0, 2000),
                (2001, A, 11, 5.0, 2000),
                (2001, A, 12, 5.0, 2000),
            ],
        )
    )

    seasons = rows(con, "SELECT season, credit FROM quality_win_season() WHERE player_id = 11")
    career = rows(
        con, "SELECT credit, seasons, best_season FROM career_quality_wins() WHERE player_id = 11"
    )

    assert career[0]["credit"] == pytest.approx(sum(r["credit"] for r in seasons))
    assert career[0]["seasons"] == 2
    assert career[0]["best_season"] == 2000


def test_an_unknown_shares_option_raises() -> None:
    con = lake(Season({A: 1500, B: 1500}, [Game("g1", A, B, True)]))

    with pytest.raises(duckdb.Error, match="shares is win_shares or minutes"):
        con.execute("SELECT * FROM quality_win_game(shares := 'bpm')").fetchall()
