from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from datetime import date, timedelta

import duckdb
import pytest

from nbalake.curate import Gate, check
from nbalake.explore import session
from nbalake.lake import Root
from nbalake.models import ALL
from tests.curated import build_models, empty_lake, gate, insert, rows, sources

NEEDED = {"arenas", "franchises", "teams", "team_seasons", "games", "team_elo", "team_games"}
UPSTREAM = tuple(m.name for m in ALL if m.name in NEEDED)
ELO = {"A": 1700.0, "B": 1600.0, "C": 1650.0, "D": 1450.0, "G": 1500.0, "H": 1520.0}
TEAM_IDS = {t: i + 1 for i, t in enumerate("ABCDEFGHPQRSTUVWX")}


def team(abbr: str) -> int:
    return TEAM_IDS[abbr]


def series(
    season: int,
    hc: str,
    other: str,
    winners: str,
    start: date,
    lg: str = "NBA",
    pattern: str = "HHAAHAH",
    neutral: bool = False,
) -> list[dict]:
    """winners has one letter per game, h when the home-court team won it."""
    games = []
    for i, w in enumerate(winners):
        home, away = (hc, other) if pattern[i] == "H" else (other, hc)
        winner = hc if w == "h" else other
        games.append(
            {
                "game_id": f"{season}-{hc}-{other}-{i + 1}",
                "season": season,
                "season_type": "playoffs",
                "lg": lg,
                "game_date": start + timedelta(days=2 * i),
                "home_team_id": team(home),
                "away_team_id": team(away),
                "home_pts": 100 if winner == home else 90,
                "away_pts": 100 if winner == away else 90,
                "winner_team_id": team(winner),
                "neutral_site": neutral,
                "source": "fte",
            }
        )
    return games


D = date.fromisoformat
GAMES = [
    *series(2016, "A", "B", "hhoohoh", D("2016-04-16")),
    *series(2016, "C", "D", "hhhh", D("2016-04-17")),
    *series(2016, "C", "A", "hohooo", D("2016-05-15")),
    *series(2016, "G", "H", "hoh", D("2016-04-20"), lg="ABA", pattern="HAH", neutral=True),
    *series(1975, "P", "X", "h", D("1975-04-01")),
    *series(1975, "P", "Q", "hoh", D("1975-04-03"), pattern="HAH"),
    *series(1975, "R", "P", "hhohh", D("1975-04-12")),
    *series(1975, "S", "T", "hhhh", D("1975-04-13")),
    *series(1975, "R", "S", "hhoohoh", D("1975-05-01")),
    *series(1954, "U", "V", "hh", D("1954-03-16"), pattern="HA"),
    *series(1954, "W", "V", "hh", D("1954-03-21"), pattern="HA"),
    *series(1954, "W", "U", "hhh", D("1954-03-27"), pattern="HAH"),
    *series(2017, "A", "B", "hhoh", D("2017-04-16")),
    *series(2017, "C", "D", "hhhh", D("2017-04-17")),
    *series(2017, "E", "F", "h", D("2017-04-18")),
]


def team_games(games: list[dict]) -> list[dict]:
    abbr = {i: t for t, i in TEAM_IDS.items()}
    out = []
    for g in games:
        for side, opp, home in (("home", "away", True), ("away", "home", False)):
            tid, oid = g[f"{side}_team_id"], g[f"{opp}_team_id"]
            out.append(
                {
                    "game_id": g["game_id"],
                    "season": g["season"],
                    "season_type": "playoffs",
                    "game_date": g["game_date"],
                    "team_id": tid,
                    "opponent_team_id": oid,
                    "is_home": home,
                    "won": g["winner_team_id"] == tid,
                    "elo_pre": ELO.get(abbr[tid], 1500.0),
                    "elo_fit_pre": ELO.get(abbr[tid], 1500.0) - 10 if g["season"] >= 2015 else None,
                }
            )
    return out


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Root:
    root = Root(tmp_path_factory.mktemp("playoffs") / "lake")
    con = empty_lake(root, sources(*UPSTREAM))
    build_models(con, *UPSTREAM)
    insert(con, "nba.games", GAMES)
    insert(con, "nba.team_games", team_games(GAMES))
    insert(
        con,
        "nba.team_elo",
        [
            {
                "game_id": tg["game_id"],
                "season": tg["season"],
                "team_id": tg["team_id"],
                "fit_edge": (60.0 if tg["is_home"] else -60.0) if tg["season"] >= 2015 else None,
            }
            for tg in team_games(GAMES)
        ],
    )
    seasons = {(g["season"], t) for g in GAMES for t in (g["home_team_id"], g["away_team_id"])}
    abbr = {i: t for t, i in TEAM_IDS.items()}
    insert(
        con,
        "nba.team_seasons",
        [
            {
                "season": s,
                "team_id": t,
                "abbreviation": abbr[t],
                "conference": "east" if abbr[t] in "AB" else "west",
            }
            for s, t in sorted(seasons)
        ],
    )
    build_models(con, "playoff_series")
    con.close()
    return root


@pytest.fixture
def con(root: Root) -> Iterator[duckdb.DuckDBPyConnection]:
    con = session.connect(root)
    yield con
    con.close()


def by_id(con: duckdb.DuckDBPyConnection) -> dict[str, dict]:
    cur = con.execute("SELECT * FROM nba.playoff_series")
    cols = [d[0] for d in cur.description or ()]
    return {r[0]: dict(zip(cols, r, strict=True)) for r in cur.fetchall()}


def dp_series_prob(e_hc: float, e_other: float, edge: float, pattern: str) -> float:
    def game(home: float, away: float) -> float:
        return 1 / (1 + 10 ** (-(home - away + edge) / 400))

    need = (len(pattern) + 1) // 2
    states, won = {(0, 0): 1.0}, 0.0
    for venue in pattern:
        p = game(e_hc, e_other) if venue == "H" else 1 - game(e_other, e_hc)
        nxt: dict[tuple[int, int], float] = defaultdict(float)
        for (a, b), q in states.items():
            if a + 1 == need:
                won += q * p
            else:
                nxt[(a + 1, b)] += q * p
            if b + 1 < need:
                nxt[(a, b + 1)] += q * (1 - p)
        states = nxt
    return won


def test_a_complete_bracket_has_rounds_formats_winners_and_next_series(
    con: duckdb.DuckDBPyConnection,
) -> None:
    s = by_id(con)
    first, other, final = s["2016-nba-a-b"], s["2016-nba-c-d"], s["2016-nba-c-a"]
    assert (first["round"], first["best_of"]) == (1, 7)
    assert (first["home_court_wins"], first["other_wins"]) == (4, 3)
    assert first["winner_team_id"] == team("A") and first["venues"] == "HHAAHAH"
    assert first["conference"] == "east" and final["conference"] is None
    assert first["next_series_id"] == other["next_series_id"] == "2016-nba-c-a"
    assert (final["round"], final["winner_team_id"]) == (2, team("A"))
    assert final["next_series_id"] is None
    assert first["game_ids"] == [f"2016-A-B-{i}" for i in range(1, 8)]
    assert (first["home_court_elo"], first["other_elo"]) == (1700.0, 1600.0)
    assert first["home_edge"] == 100


def test_leagues_in_one_season_are_separate_brackets_and_neutral_series_have_no_home_edge(
    con: duckdb.DuckDBPyConnection,
) -> None:
    aba = by_id(con)["2016-aba-g-h"]
    assert (aba["lg"], aba["round"], aba["best_of"], aba["next_series_id"]) == ("ABA", 1, 3, None)
    assert aba["venues"] == "NNN" and aba["home_edge"] == 0 and aba["fit_home_edge"] == 0


def test_byes_number_rounds_from_the_final_and_tiebreaker_games_are_not_series(
    con: duckdb.DuckDBPyConnection,
) -> None:
    s = by_id(con)
    rounds = {k: v["round"] for k, v in s.items() if v["season"] == 1975}
    assert rounds == {"1975-nba-p-q": 1, "1975-nba-r-p": 2, "1975-nba-s-t": 2, "1975-nba-r-s": 3}
    members = [g for v in s.values() for g in v["game_ids"]]
    assert "1975-P-X-1" not in members


def test_a_season_that_is_not_an_elimination_bracket_is_left_out(
    con: duckdb.DuckDBPyConnection,
) -> None:
    assert rows(con, "SELECT count(*) FROM nba.playoff_series WHERE season = 1954") == [(0,)]


def test_the_latest_season_takes_each_rounds_format_from_the_previous_season(
    con: duckdb.DuckDBPyConnection,
) -> None:
    s = by_id(con)
    open_, done, game_one = s["2017-nba-a-b"], s["2017-nba-c-d"], s["2017-nba-e-f"]
    assert (open_["best_of"], open_["winner_team_id"], open_["home_court_wins"]) == (7, None, 3)
    assert (done["best_of"], done["winner_team_id"], done["next_series_id"]) == (7, team("C"), None)
    assert (game_one["best_of"], game_one["winner_team_id"], game_one["round"]) == (7, None, 1)


def test_series_probability_matches_a_game_by_game_walk_of_the_venues(
    con: duckdb.DuckDBPyConnection,
) -> None:
    for v in by_id(con).values():
        pattern = {7: "HHAAHAH", 5: "HHAAH", 3: "HAH"}[v["best_of"]]
        expected = dp_series_prob(v["home_court_elo"], v["other_elo"], v["home_edge"], pattern)
        assert v["home_court_series_prob"] == pytest.approx(expected, abs=1e-12), v["series_id"]
        if v["home_court_elo_fit"] is not None:
            fit = dp_series_prob(
                v["home_court_elo_fit"], v["other_elo_fit"], v["fit_home_edge"], pattern
            )
            assert v["home_court_series_prob_fit"] == pytest.approx(fit, abs=1e-12)


def test_the_series_macro_reproduces_the_table_even_beside_same_named_columns(
    con: duckdb.DuckDBPyConnection,
) -> None:
    mismatched = rows(
        con,
        "SELECT series_id FROM nba.playoff_series "
        "WHERE abs(elo_series_prob(home_court_elo, other_elo, best_of, home_edge) "
        "          - home_court_series_prob) > 1e-12",
    )
    assert mismatched == []
    fixed = rows(
        con,
        "SELECT DISTINCT elo_series_prob(1500, 1500, 1, 0), elo_game_prob(1500, 1500) "
        "FROM nba.playoff_series",
    )
    assert fixed == [(pytest.approx(0.5), pytest.approx(1 / (1 + 10 ** (-100 / 400))))]


def test_the_macros_agree_with_the_walk_on_a_grid(con: duckdb.DuckDBPyConnection) -> None:
    for best_of, pattern in ((1, "H"), (3, "HAH"), (5, "HHAAH"), (7, "HHAAAHH")):
        for diff in (-300, -50, 0, 120):
            for edge in (0, 64, 100):
                sql = "SELECT elo_series_prob(?, 1500, ?, ?)"
                ((got,),) = rows(con, sql, (1500 + diff, best_of, edge))
                want = dp_series_prob(1500 + diff, 1500, edge, pattern)
                assert got == pytest.approx(want, abs=1e-12)


def test_playoff_series_gates_pass_on_a_consistent_bracket(con: duckdb.DuckDBPyConnection) -> None:
    for name in (
        "games_playoff_series_key_unique",
        "games_playoff_series_winner_won_the_majority",
        "games_playoff_series_next_is_the_winners_following_round",
    ):
        assert check(con, gate(name)).ok, name


def test_the_bracket_gate_checks_complete_seasons_since_1984_and_skips_one_in_progress(
    con: duckdb.DuckDBPyConnection,
) -> None:
    result = check(con, gate("games_playoff_series_since_1984_one_bracket_of_15_in_4_rounds"))
    assert [(r["season"], r["series"], r["rounds"]) for r in result.sample] == [(2016, 3, 2)]


def test_the_membership_gate_flags_playoff_games_outside_every_series_since_1984(
    con: duckdb.DuckDBPyConnection,
) -> None:
    membership = gate("games_playoff_series_games_belong_to_one_series_since_1984")
    assert check(con, membership).ok
    without = Gate(
        membership.name,
        membership.sql.replace(
            "FROM nba.playoff_series",
            "FROM (SELECT * FROM nba.playoff_series WHERE series_id <> '2016-nba-c-d')",
        ),
    )
    flagged = check(con, without)
    assert flagged.violations == 4
    assert {r["game_id"] for r in flagged.sample} <= {f"2016-C-D-{i}" for i in range(1, 5)}
