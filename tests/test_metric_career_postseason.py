from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import duckdb
import pytest

from nbalake.explore import macros

A, B, C, D = 1, 2, 3, 4
NEEDS = {
    "elo_game_prob",
    "postseason_team_credit",
    "postseason_game_credit",
    "postseason_season_credit",
    "career_postseason",
    "postseason_basic_season_credit",
    "career_postseason_basic",
}


@dataclass(frozen=True, slots=True)
class Game:
    game_id: str
    home: int
    away: int
    home_won: bool
    round: int = 1
    day: str = "1995-05-01"
    season: int = 1995
    neutral: bool = False


@dataclass
class Playoffs:
    elo: dict[int, float]
    games: list[Game]
    fit_edge: float | None = None
    box: list[tuple[str, int, int, int, bool]] = field(default_factory=list)
    regular: list[tuple[int, int, int, float | None, int]] = field(default_factory=list)
    win_shares: list[tuple[int, int, int, float]] = field(default_factory=list)
    points: dict[tuple[str, int], int] = field(default_factory=dict)
    regular_box: list[tuple[int, int, int, int, int]] = field(default_factory=list)


def lake(p: Playoffs) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("CREATE SCHEMA nba")
    con.execute(
        "CREATE TABLE nba.playoff_series (season INTEGER, lg VARCHAR, round INTEGER, "
        "series_id VARCHAR, game_ids VARCHAR[])"
    )
    con.execute(
        "CREATE TABLE nba.games (game_id VARCHAR, season_type VARCHAR, neutral_site BOOLEAN, "
        "home_team_id BIGINT)"
    )
    con.execute(
        "CREATE TABLE nba.team_games (game_id VARCHAR, game_date DATE, team_id BIGINT, "
        "opponent_team_id BIGINT, won BOOLEAN, is_home BOOLEAN, elo_pre DOUBLE, elo_fit_pre DOUBLE)"
    )
    con.execute("CREATE TABLE nba.team_elo (game_id VARCHAR, team_id BIGINT, fit_edge DOUBLE)")
    con.execute(
        "CREATE TABLE nba.player_box (game_id VARCHAR, season INTEGER, team_id BIGINT, "
        "player_id HUGEINT, seconds INTEGER, played BOOLEAN, pts BIGINT, fgm BIGINT, fga BIGINT, "
        "fta BIGINT, ftm BIGINT, oreb BIGINT, dreb BIGINT, stl BIGINT, ast BIGINT, blk BIGINT, "
        "pf BIGINT, tov BIGINT)"
    )
    con.execute(
        "CREATE TABLE nba.player_seasons (season INTEGER, lg VARCHAR, team_id BIGINT, "
        "player_id HUGEINT, bpm DOUBLE, mp BIGINT, ws DOUBLE)"
    )
    con.execute("CREATE TABLE nba.players (player_id HUGEINT, name VARCHAR)")
    for g in p.games:
        series = f"{g.season}-{g.round}-{min(g.home, g.away)}-{max(g.home, g.away)}"
        con.execute(
            "INSERT INTO nba.playoff_series VALUES (?, 'NBA', ?, ?, [?])",
            [g.season, g.round, series, g.game_id],
        )
        con.execute(
            "INSERT INTO nba.games VALUES (?, 'playoffs', ?, ?)", [g.game_id, g.neutral, g.home]
        )
        fitted = p.fit_edge is not None
        for team, opp, home, won in (
            (g.home, g.away, True, g.home_won),
            (g.away, g.home, False, not g.home_won),
        ):
            con.execute(
                "INSERT INTO nba.team_games VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    g.game_id,
                    g.day,
                    team,
                    opp,
                    won,
                    home,
                    p.elo[team],
                    p.elo[team] if fitted else None,
                ],
            )
            con.execute("INSERT INTO nba.team_elo VALUES (?, ?, ?)", [g.game_id, team, p.fit_edge])
    season_of = {g.game_id: g.season for g in p.games}
    for game_id, team, player, seconds, played in p.box:
        box_row(
            con,
            game_id,
            season_of[game_id],
            team,
            player,
            seconds,
            played,
            p.points.get((game_id, player), 0),
        )
    for season, team, player, seconds, pts in p.regular_box:
        game_id = f"r{season}-{team}-{player}"
        con.execute("INSERT INTO nba.games VALUES (?, 'regular', false, ?)", [game_id, team])
        box_row(con, game_id, season, team, player, seconds, True, pts)
    for season, team, player, bpm, mp in p.regular:
        con.execute(
            "INSERT INTO nba.player_seasons VALUES (?, 'NBA', ?, ?, ?, ?, NULL)",
            [season, team, player, bpm, mp],
        )
    for season, team, player, ws in p.win_shares:
        con.execute(
            "INSERT INTO nba.player_seasons VALUES (?, 'NBA', ?, ?, NULL, NULL, ?)",
            [season, team, player, ws],
        )
    for m in macros.shipped():
        if m.name in NEEDS:
            con.execute(m.sql)
    return con


def box_row(
    con: duckdb.DuckDBPyConnection,
    game_id: str,
    season: int,
    team: int,
    player: int,
    seconds: int,
    played: bool,
    pts: int,
) -> None:
    con.execute(
        "INSERT INTO nba.player_box VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)",
        [game_id, season, team, player, seconds, played, pts],
    )


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cur = con.execute(sql)
    names = [d[0] for d in cur.description or ()]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]


def team_credit(con: duckdb.DuckDBPyConnection, game_id: str, team: int, args: str = "") -> float:
    found = rows(
        con,
        f"SELECT DISTINCT team_credit FROM postseason_game_credit({args}) "
        f"WHERE game_id = '{game_id}' AND team_id = {team}",
    )
    assert len(found) == 1
    return found[0]["team_credit"]


def even_box(*games: Game) -> list[tuple[str, int, int, int, bool]]:
    return [(g.game_id, t, t * 10, 2880, True) for g in games for t in (g.home, g.away)]


def even_regular(season: int, *teams: int) -> list[tuple[int, int, int, float | None, int]]:
    return [(season, t, t * 10, 0.0, 2000) for t in teams]


def test_a_teams_game_credit_splits_across_its_players_and_sums_to_five_times_the_team_credit() -> (
    None
):
    g = Game("g1", A, B, True)
    p = Playoffs(
        {A: 1600, B: 1500},
        [g],
        box=[
            ("g1", A, 11, 2400, True),
            ("g1", A, 12, 1200, True),
            ("g1", A, 13, 600, True),
            *even_box(g)[1:],
        ],
        regular=[(1995, A, 11, 6.0, 3000), (1995, A, 12, 1.0, 2000), (1995, A, 13, -1.0, 500)],
    )
    con = lake(p)

    found = rows(
        con,
        "SELECT player_id, share, credit, team_credit FROM postseason_game_credit() "
        "WHERE team_id = 1",
    )

    assert sum(r["share"] for r in found) == pytest.approx(1.0)
    assert sum(r["credit"] for r in found) == pytest.approx(5 * found[0]["team_credit"])
    share = {r["player_id"]: r["share"] for r in found}
    weights = {11: 2400 * 8, 12: 1200 * 3, 13: 600 * 1}
    assert share == pytest.approx({k: v / sum(weights.values()) for k, v in weights.items()})


def test_beating_a_stronger_opponent_earns_more_than_beating_a_weaker_one() -> None:
    games = [Game("strong", A, B, True), Game("weak", A, C, True)]
    con = lake(Playoffs({A: 1600, B: 1650, C: 1450}, games, box=even_box(*games)))

    assert team_credit(con, "strong", A) > team_credit(con, "weak", A) > 0


def test_losing_to_a_great_team_costs_less_than_losing_to_a_weak_one() -> None:
    games = [Game("to_great", B, A, True), Game("to_weak", C, A, True)]
    con = lake(Playoffs({A: 1600, B: 1750, C: 1450}, games, box=even_box(*games)))

    assert team_credit(con, "to_weak", A) < team_credit(con, "to_great", A) < 0


def test_a_swept_team_earns_no_positive_credit() -> None:
    games = [Game(f"g{i}", A, B, True, day=f"1995-05-0{i}") for i in range(1, 5)]
    con = lake(Playoffs({A: 1700, B: 1450}, games, box=even_box(*games)))

    found = rows(con, "SELECT credit FROM postseason_game_credit() WHERE team_id = 2")
    swept = rows(con, "SELECT credit FROM postseason_season_credit() WHERE team_id = 2")

    assert len(found) == 4
    assert all(r["credit"] < 0 for r in found)
    assert swept[0]["credit"] < 0


def test_against_the_weakest_teams_equal_at_a_neutral_site_the_baseline_is_a_coin_flip() -> None:
    g = Game("bubble", A, B, True, neutral=True, round=2)
    con = lake(Playoffs({A: 1600, B: 1500}, [g], box=even_box(g)))

    found = rows(
        con,
        "SELECT team_id, baseline_elo, baseline_win_prob, team_credit "
        "FROM postseason_game_credit()",
    )

    by_team = {r["team_id"]: r for r in found}
    assert by_team[A]["baseline_elo"] == 1500
    assert by_team[A]["baseline_win_prob"] == pytest.approx(0.5)
    assert by_team[A]["team_credit"] == pytest.approx(2 * 0.5)
    assert by_team[B]["team_credit"] == pytest.approx(-2 / (1 + 10 ** (100 / 400)))


def test_linear_rounds_weigh_a_finals_game_four_first_round_games_and_flat_weighs_all_one() -> None:
    games = [
        Game("first", A, B, True, round=1),
        Game("finals", A, B, True, round=4, day="1995-06-01"),
    ]
    con = lake(Playoffs({A: 1600, B: 1500}, games, box=even_box(*games)))

    linear = team_credit(con, "finals", A) / team_credit(con, "first", A)
    flat = team_credit(con, "finals", A, "rounds := 'flat'") / team_credit(
        con, "first", A, "rounds := 'flat'"
    )

    assert linear == pytest.approx(4)
    assert flat == pytest.approx(1)


def test_the_baseline_is_each_teams_elo_entering_its_first_playoff_game() -> None:
    games = [
        Game("ab", A, B, True, day="1995-05-01"),
        Game("cd", C, D, True, day="1995-05-02"),
    ]
    con = lake(Playoffs({A: 1700, B: 1400, C: 1600, D: 1500}, games, box=even_box(*games)))

    weakest = rows(con, "SELECT DISTINCT baseline_elo FROM postseason_game_credit()")
    average = rows(
        con, "SELECT DISTINCT baseline_elo FROM postseason_game_credit(baseline := 'average')"
    )

    assert weakest == [{"baseline_elo": 1400}]
    assert average == [{"baseline_elo": pytest.approx(1550)}]


def test_the_home_edge_is_100_before_fitted_elo_and_the_fitted_edge_where_it_exists() -> None:
    g = Game("g1", A, B, True)
    fte = lake(Playoffs({A: 1600, B: 1500}, [g], box=even_box(g)))
    fitted = lake(Playoffs({A: 1600, B: 1500}, [g], box=even_box(g), fit_edge=62.5))

    query = "SELECT team_id, venue_edge FROM postseason_game_credit() ORDER BY team_id"

    assert [r["venue_edge"] for r in rows(fte, query)] == [100, -100]
    assert [r["venue_edge"] for r in rows(fitted, query)] == [62.5, -62.5]


def test_from_1994_a_player_who_sat_out_a_game_gets_nothing_from_it() -> None:
    games = [Game("g1", A, B, True), Game("g2", A, B, False, day="1995-05-03")]
    box = [
        ("g1", A, 11, 2000, True),
        ("g1", A, 12, 2000, True),
        ("g2", A, 11, 0, False),
        ("g2", A, 12, 2000, True),
        *[r for r in even_box(*games) if r[1] == B],
    ]
    con = lake(Playoffs({A: 1600, B: 1550}, games, box=box))

    found = rows(
        con,
        "SELECT game_id, player_id, share_basis FROM postseason_game_credit() WHERE team_id = 1",
    )

    assert {(r["game_id"], r["player_id"]) for r in found} == {("g1", 11), ("g1", 12), ("g2", 12)}
    assert {r["share_basis"] for r in found} == {"playoff minutes"}


def test_before_1994_shares_come_from_regular_season_minutes_and_bpm_under_minus_2_is_0() -> None:
    g = Game("old", A, B, True, season=1990, day="1990-05-01")
    regular = [
        (1990, A, 11, 4.0, 3000),
        (1990, A, 12, 0.0, 1500),
        (1990, A, 13, -5.0, 2500),
        (1990, A, 14, None, 900),
        *even_regular(1990, B),
    ]
    con = lake(Playoffs({A: 1600, B: 1500}, [g], regular=regular))

    found = rows(
        con, "SELECT player_id, share, share_basis FROM postseason_game_credit() WHERE team_id = 1"
    )

    share = {r["player_id"]: r["share"] for r in found}
    assert share == pytest.approx({11: 18000 / 21000, 12: 3000 / 21000, 13: 0.0, 14: 0.0})
    assert {r["share_basis"] for r in found} == {"regular season minutes"}


def test_before_1984_nothing_counts() -> None:
    g = Game("early", A, B, True, season=1983, day="1983-05-01")
    con = lake(Playoffs({A: 1600, B: 1500}, [g], regular=even_regular(1983, A, B)))

    assert rows(con, "FROM postseason_game_credit()") == []


def test_season_credit_sums_games_and_career_credit_sums_seasons_ranked_by_credit() -> None:
    games = [
        Game("a", A, B, True, season=1995, day="1995-05-01", round=4),
        Game("b", A, B, False, season=1996, day="1996-05-01"),
        Game("c", A, B, True, season=1996, day="1996-05-03"),
    ]
    con = lake(Playoffs({A: 1600, B: 1500}, games, box=even_box(*games)))
    con.execute("INSERT INTO nba.players VALUES (10, 'Ace'), (20, 'Bee')")

    by_game = rows(
        con,
        "SELECT season, player_id, sum(credit) AS credit "
        "FROM postseason_game_credit() GROUP BY ALL",
    )
    by_season = rows(con, "SELECT season, player_id, credit, games FROM postseason_season_credit()")
    career = rows(con, "FROM career_postseason()")

    assert {(r["season"], r["player_id"]): r["credit"] for r in by_season} == pytest.approx(
        {(r["season"], r["player_id"]): r["credit"] for r in by_game}
    )
    assert [r["player"] for r in career] == ["Ace", "Bee"]
    assert [r["rank"] for r in career] == [1, 2]
    ace = career[0]
    assert ace["runs"] == 2
    assert ace["credit"] == pytest.approx(
        sum(r["credit"] for r in by_season if r["player_id"] == 10)
    )
    assert ace["best_season"] == 1995


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ("baseline := 'median'", "baseline is weakest or average"),
        ("rounds := 'squared'", "rounds is linear, from_final, or flat"),
    ],
)
def test_an_unknown_baseline_or_rounds_value_raises_naming_the_allowed_values(
    args: str, message: str
) -> None:
    g = Game("g1", A, B, True)
    con = lake(Playoffs({A: 1600, B: 1500}, [g], box=even_box(g)))

    with pytest.raises(duckdb.Error, match=message):
        con.execute(f"FROM career_postseason({args})").fetchall()


def test_a_game_where_no_player_has_bpm_weight_splits_by_minutes_alone() -> None:
    g = Game("g1", A, B, True)
    box = [("g1", A, 11, 2000, True), ("g1", A, 12, 500, True), ("g1", B, 21, 2000, True)]
    con = lake(Playoffs({A: 1600, B: 1500}, [g], box=box, regular=[(1995, A, 11, -3.0, 2000)]))

    found = rows(con, "SELECT player_id, share FROM postseason_game_credit() WHERE team_id = 1")

    assert {r["player_id"]: r["share"] for r in found} == pytest.approx({11: 0.8, 12: 0.2})


def run_with_points(
    a_points: tuple[int, int],
    regular_points: tuple[int, int] = (1000, 1000),
    seconds: int = 2880,
    regular_seconds: int = 60 * 2000,
) -> duckdb.DuckDBPyConnection:
    """Team A's players 11 and 12 split one playoff game evenly by minutes and BPM, team B
    plays one man, and points alone set Game Score."""
    g = Game("g1", A, B, True)
    box = [("g1", A, 11, seconds, True), ("g1", A, 12, seconds, True), ("g1", B, 21, 2880, True)]
    regular: list[tuple[int, int, int, float | None, int]] = [
        (1995, A, 11, 0.0, 2000),
        (1995, A, 12, 0.0, 2000),
        (1995, B, 21, 0.0, 2000),
    ]
    regular_box = [
        (1995, A, 11, regular_seconds, regular_points[0]),
        (1995, A, 12, regular_seconds, regular_points[1]),
    ]
    points = {("g1", 11): a_points[0], ("g1", 12): a_points[1]}
    return lake(
        Playoffs(
            {A: 1600, B: 1500},
            [g],
            box=box,
            regular=regular,
            points=points,
            regular_box=regular_box,
        )
    )


def shares_and_adjustments(
    con: duckdb.DuckDBPyConnection, args: str = ""
) -> dict[int, tuple[float, float]]:
    found = rows(
        con,
        f"SELECT player_id, share, playoff_bpm_adjustment FROM postseason_game_credit({args}) "
        "WHERE team_id = 1",
    )
    return {r["player_id"]: (r["share"], r["playoff_bpm_adjustment"]) for r in found}


def test_outplaying_the_regular_season_beside_a_teammate_moves_share_to_the_better_one() -> None:
    con = run_with_points((40, 10))

    found = shares_and_adjustments(con)

    gain = {
        11: 2160 * 40 / 2880 - 2160 * 1000 / 120000,
        12: 2160 * 10 / 2880 - 2160 * 1000 / 120000,
    }
    mean = (gain[11] + gain[12]) / 2
    shrink = 48 / (48 + 750)
    adjustment = {p: 0.6 * (g - mean) * shrink for p, g in gain.items()}
    assert {p: a for p, (_, a) in found.items()} == pytest.approx(adjustment)
    weight = {p: 2 + adjustment[p] for p in (11, 12)}
    assert {p: s for p, (s, _) in found.items()} == pytest.approx(
        {p: w / sum(weight.values()) for p, w in weight.items()}
    )


def test_a_drop_every_player_shares_moves_no_share() -> None:
    con = run_with_points((10, 10), regular_points=(2000, 2000))

    found = shares_and_adjustments(con)

    assert {p: s for p, (s, _) in found.items()} == pytest.approx({11: 0.5, 12: 0.5})
    assert {p: a for p, (_, a) in found.items()} == pytest.approx({11: 0.0, 12: 0.0})


def test_the_adjustment_is_half_the_observed_gain_at_750_playoff_minutes() -> None:
    short = shares_and_adjustments(run_with_points((40, 10)))
    long = shares_and_adjustments(run_with_points((625, 125), seconds=60 * 750))

    assert long[11][1] - long[12][1] == pytest.approx(0.6 * (30 - 6) * 750 / 1500)
    assert short[11][1] - short[12][1] == pytest.approx(0.6 * (30 - 7.5) * 48 / 798)


def test_under_500_regular_season_minutes_there_is_no_adjustment() -> None:
    found = shares_and_adjustments(run_with_points((40, 10), regular_seconds=60 * 499))

    assert {p: a for p, (_, a) in found.items()} == {11: 0.0, 12: 0.0}


def test_playoff_adjustment_false_weighs_by_regular_season_bpm_alone() -> None:
    found = shares_and_adjustments(run_with_points((40, 10)), "playoff_adjustment := false")

    assert found == {11: (0.5, 0.0), 12: (0.5, 0.0)}
