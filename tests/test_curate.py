from __future__ import annotations

import json
import re
from collections.abc import Iterator, Sequence
from datetime import date
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import nbalake
from nbalake import profile as profile_module
from nbalake.curate import (
    Gate,
    GateFailure,
    GateResult,
    Step,
    build,
    check,
    curate,
    seed_sql,
    shipped_gates,
    shipped_steps,
)
from nbalake.lake import Layout, Root, columns, connect, layout, table_exists, transaction
from nbalake.models import ALL as MODELS
from nbalake.models import GROUPS, Chunk, Kind, Model
from tests.curated import GATES, SCORES_GATE, STAGED, STEPS, UNIQUE_GATE, empty_lake, insert

SQL_DIR = Path(nbalake.__file__).parent / "sql"
GAMES_TABLE = 'lake."nba"."games"'

BOS, DEN, LAL = 1610612738, 1610612743, 1610612747
ABBR = {BOS: "BOS", DEN: "DEN", LAL: "LAL"}

SCHEDULE_DDL = """
CREATE TABLE sdv.nba_stats_schedules (
    season INTEGER, season_type VARCHAR, game_id VARCHAR, game_date VARCHAR,
    home_team_id BIGINT, home_team_abbreviation VARCHAR,
    away_team_id BIGINT, away_team_abbreviation VARCHAR,
    home_pts INTEGER, away_pts INTEGER
)
"""
TEAM_BOX_DDL = (
    "CREATE TABLE sdv.nba_stats_team_boxscores (game_id VARCHAR, team_id BIGINT, points INTEGER)"
)


def game(
    season: int,
    game_id: str,
    game_date: str,
    home: int,
    away: int,
    home_pts: int,
    away_pts: int,
    season_type: str = "Regular Season",
) -> dict:
    return {
        "season": season,
        "season_type": season_type,
        "game_id": game_id,
        "game_date": game_date,
        "home_team_id": home,
        "home_team_abbreviation": ABBR[home],
        "away_team_id": away,
        "away_team_abbreviation": ABBR[away],
        "home_pts": home_pts,
        "away_pts": away_pts,
    }


GAMES = [
    game(2025, "0022400300", "2025-01-10", BOS, LAL, 110, 100),
    game(2024, "0022300002", "2023-10-24", LAL, DEN, 95, 101),
    game(2025, "0022400001", "2024-10-22", DEN, BOS, 100, 100),
    game(2024, "0042300101", "2024-04-20", BOS, LAL, 99, 97, season_type="Playoffs"),
    game(2024, "0022300001", "2023-10-24", BOS, DEN, 120, 110),
]
WINNERS = {
    "0022400300": BOS,
    "0022300002": DEN,
    "0022400001": None,
    "0042300101": BOS,
    "0022300001": BOS,
}
DUPLICATED = "0022300001"


class Abort(Exception):
    pass


def add_games(con: duckdb.DuckDBPyConnection, games: Sequence[dict]) -> None:
    boxes = [
        {"game_id": g["game_id"], "team_id": g[f"{side}_team_id"], "points": g[f"{side}_pts"]}
        for g in games
        for side in ("home", "away")
    ]
    con.register("schedule_rows", pa.Table.from_pylist(list(games)))
    con.register("box_rows", pa.Table.from_pylist(boxes))
    con.execute("INSERT INTO sdv.nba_stats_schedules BY NAME SELECT * FROM schedule_rows")
    con.execute("INSERT INTO sdv.nba_stats_team_boxscores BY NAME SELECT * FROM box_rows")
    con.unregister("schedule_rows")
    con.unregister("box_rows")


def duplicate_game(con: duckdb.DuckDBPyConnection, game_id: str) -> None:
    """Stands in for a stage of a unit that repeats a game, so it records the unit as stage does."""
    with transaction(con):
        con.execute(
            "INSERT INTO sdv.nba_stats_schedules "
            "SELECT * FROM sdv.nba_stats_schedules WHERE game_id = ?",
            [game_id],
        )
        con.execute(
            "INSERT INTO lake.meta.staged_units VALUES "
            "('sdv.nba_stats_schedules', ?, 'dup', '', 1, now())",
            [f"duplicate_{game_id}"],
        )


def scalar(con: duckdb.DuckDBPyConnection, sql: str, params: Sequence[object] = ()) -> object:
    row = con.execute(sql, list(params)).fetchone()
    assert row is not None
    return row[0]


def games_count(con: duckdb.DuckDBPyConnection) -> object:
    return scalar(con, "SELECT count(*) FROM nba.games")


def games_rows(con: duckdb.DuckDBPyConnection, version: int | None = None) -> list[tuple]:
    at = f" AT (VERSION => {version})" if version is not None else ""
    return con.execute(f"SELECT * FROM nba.games{at} ORDER BY game_date, game_id").fetchall()


def recorded_gates(con: duckdb.DuckDBPyConnection, run_id: str) -> dict[str, tuple[int, list]]:
    rows = con.execute(
        "SELECT gate, violations, sample FROM lake.meta.gate_results WHERE run_id = ?", [run_id]
    ).fetchall()
    return {gate: (violations, json.loads(sample)) for gate, violations, sample in rows}


def newest_snapshot(con: duckdb.DuckDBPyConnection) -> int:
    return int(str(scalar(con, "SELECT max(snapshot_id) FROM lake.snapshots()")))


def table_id(con: duckdb.DuckDBPyConnection, name: str) -> str:
    return str(scalar(con, "SELECT table_id FROM lake.table_info() WHERE table_name = ?", [name]))


@pytest.fixture
def staged(root: Root) -> Iterator[duckdb.DuckDBPyConnection]:
    con = connect(root, schemas=("sdv",))
    con.execute(SCHEDULE_DDL)
    con.execute(TEAM_BOX_DDL)
    add_games(con, GAMES)
    yield con
    con.close()


@pytest.fixture
def reader(root: Root, staged: duckdb.DuckDBPyConnection) -> Iterator[duckdb.DuckDBPyConnection]:
    con = connect(root, read_only=True)
    yield con
    con.close()


def test_curate_builds_games_with_winner_team_and_null_on_tie(
    staged: duckdb.DuckDBPyConnection,
) -> None:
    assert not table_exists(staged, "nba", "games")

    report = curate(staged, steps=STEPS, gates=GATES, run_id="r1")

    assert report.committed and report.rows == {"games": len(GAMES)}
    assert all(g.ok for g in report.gates)
    assert table_exists(staged, "nba", "games")
    typed = columns(staged, GAMES_TABLE)
    assert (typed["season"], typed["game_date"]) == ("INTEGER", "DATE")
    winners = dict(staged.execute("SELECT game_id, winner_team_id FROM nba.games").fetchall())
    assert winners == WINNERS
    assert staged.execute(
        "SELECT game_id, game_date FROM nba.games ORDER BY game_date, game_id LIMIT 1"
    ).fetchall() == [("0022300001", date(2023, 10, 24))]


def test_games_files_are_partitioned_by_season_and_sorted_by_date_then_id(
    root: Root, staged: duckdb.DuckDBPyConnection
) -> None:
    curate(staged, steps=STEPS, gates=GATES, run_id="r1")

    partitions = sorted(p for p in root.data.rglob("season=*") if p.is_dir())
    assert [p.name for p in partitions] == ["season=2024", "season=2025"]
    rows_seen = 0
    for partition in partitions:
        season = int(partition.name.removeprefix("season="))
        staged_order = [(g["game_date"], g["game_id"]) for g in GAMES if g["season"] == season]
        assert staged_order != sorted(staged_order)
        for file in partition.glob("*.parquet"):
            rows = pq.read_table(file).to_pylist()
            keys = [(r["game_date"].isoformat(), r["game_id"]) for r in rows]
            assert {r["season"] for r in rows} == {season}
            assert len(keys) > 1 and keys == sorted(keys)
            rows_seen += len(rows)
    assert rows_seen == len(GAMES)


def test_passing_gates_are_recorded_with_zero_violations_and_an_empty_sample(
    staged: duckdb.DuckDBPyConnection,
) -> None:
    report = curate(staged, steps=STEPS, gates=GATES, run_id="r1")

    assert [g.gate for g in report.gates] == [g.name for g in GATES]
    assert recorded_gates(staged, "r1") == {g.name: (0, []) for g in GATES}


def test_curate_rebuilds_games_rather_than_appending(staged: duckdb.DuckDBPyConnection) -> None:
    first = curate(staged, steps=STEPS, gates=GATES, run_id="r1")
    second = curate(staged, steps=STEPS, gates=GATES, run_id="r2", rebuild=True)

    assert first.rows == second.rows == {"games": len(GAMES)}
    assert games_count(staged) == len(GAMES)
    assert set(recorded_gates(staged, "r1")) == set(recorded_gates(staged, "r2"))


def test_duplicate_game_id_fails_the_unique_gate_and_rolls_games_back(
    staged: duckdb.DuckDBPyConnection,
) -> None:
    curate(staged, steps=STEPS, gates=GATES, run_id="r1")
    published = games_rows(staged)
    duplicate_game(staged, DUPLICATED)

    with pytest.raises(GateFailure) as failure:
        curate(staged, steps=STEPS, gates=GATES, run_id="r2")

    assert str(failure.value) == f"quality gates failed: {UNIQUE_GATE} (1 violations)"
    (failed,) = [r for r in failure.value.results if not r.ok]
    assert (failed.gate, failed.violations) == (UNIQUE_GATE, 1)
    assert games_rows(staged) == published
    recorded = recorded_gates(staged, "r2")
    assert set(recorded) == {g.name for g in GATES}
    assert recorded.pop(UNIQUE_GATE) == (1, [{"game_id": DUPLICATED, "n": 2}])
    assert all(result == (0, []) for result in recorded.values())


def test_failed_first_curate_publishes_no_games_table(staged: duckdb.DuckDBPyConnection) -> None:
    duplicate_game(staged, DUPLICATED)

    with pytest.raises(GateFailure):
        curate(staged, steps=STEPS, gates=GATES, run_id="r1")

    assert not table_exists(staged, "nba", "games")
    assert recorded_gates(staged, "r1")[UNIQUE_GATE][0] == 1


def test_score_mismatch_with_team_box_names_the_offending_game(
    staged: duckdb.DuckDBPyConnection,
) -> None:
    mismatched = GAMES[0]
    staged.execute(
        "UPDATE sdv.nba_stats_team_boxscores SET points = points + 1 "
        "WHERE game_id = ? AND team_id = ?",
        [mismatched["game_id"], mismatched["home_team_id"]],
    )

    with pytest.raises(GateFailure) as failure:
        curate(staged, steps=STEPS, gates=GATES, run_id="r1")

    (failed,) = [r for r in failure.value.results if not r.ok]
    assert (failed.gate, failed.violations) == (SCORES_GATE, 1)
    assert failed.sample == [
        {
            "game_id": mismatched["game_id"],
            "home_pts": mismatched["home_pts"],
            "away_pts": mismatched["away_pts"],
            "home_box_pts": mismatched["home_pts"] + 1,
            "away_box_pts": mismatched["away_pts"],
        }
    ]
    assert recorded_gates(staged, "r1")[SCORES_GATE] == (1, failed.sample)


def test_enforce_gates_off_commits_violations_and_reports_the_failing_gate(
    staged: duckdb.DuckDBPyConnection,
) -> None:
    curate(staged, steps=STEPS, gates=GATES, run_id="r1")
    duplicate_game(staged, DUPLICATED)

    report = curate(staged, steps=STEPS, gates=GATES, run_id="r2", enforce_gates=False)

    assert report.committed and report.rows == {"games": len(GAMES) + 1}
    assert [g.gate for g in report.gates if not g.ok] == [UNIQUE_GATE]
    assert games_count(staged) == len(GAMES) + 1
    assert recorded_gates(staged, "r2")[UNIQUE_GATE][0] == 1


def test_failed_curate_adds_only_one_gate_result_snapshot_and_keeps_the_games_table(
    staged: duckdb.DuckDBPyConnection,
) -> None:
    curate(staged, steps=STEPS, gates=GATES, run_id="r1")
    duplicate_game(staged, DUPLICATED)
    before = newest_snapshot(staged)
    games_id = table_id(staged, "games")

    with pytest.raises(GateFailure):
        curate(staged, steps=STEPS, gates=GATES, run_id="r2")

    added = staged.execute(
        "SELECT changes FROM lake.snapshots() WHERE snapshot_id > ? ORDER BY snapshot_id",
        [before],
    ).fetchall()
    gate_results_id = table_id(staged, "gate_results")
    assert added == [({"tables_inserted_into": [gate_results_id]},)]
    assert table_id(staged, "games") == games_id
    assert games_rows(staged) == games_rows(staged, version=before)


def test_reader_sees_the_committed_snapshot_while_a_rebuild_is_open(
    staged: duckdb.DuckDBPyConnection, reader: duckdb.DuckDBPyConnection
) -> None:
    curate(staged, steps=STEPS, gates=GATES, run_id="r1")
    duplicate_game(staged, DUPLICATED)

    with pytest.raises(Abort), transaction(staged):
        assert build(staged, STEPS[0]) == len(GAMES) + 1
        assert games_count(staged) == len(GAMES) + 1
        assert games_count(reader) == len(GAMES)
        raise Abort

    assert games_count(reader) == len(GAMES)
    with pytest.raises(GateFailure):
        curate(staged, steps=STEPS, gates=GATES, run_id="r2")
    assert games_count(reader) == len(GAMES)
    curate(staged, steps=STEPS, gates=GATES, run_id="r3", enforce_gates=False)
    assert games_count(reader) == len(GAMES) + 1


def test_check_counts_every_violation_and_caps_the_sample(
    staged: duckdb.DuckDBPyConnection,
) -> None:
    extra = [
        game(2025, f"00224001{i:02d}", f"2025-02-{i:02d}", BOS, LAL, 100 + i, 90)
        for i in range(1, 4)
    ]
    add_games(staged, extra)
    staged.execute("INSERT INTO sdv.nba_stats_schedules SELECT * FROM sdv.nba_stats_schedules")
    distinct_games = len(GAMES) + len(extra)

    report = curate(staged, steps=STEPS, gates=GATES, run_id="r1", enforce_gates=False)
    capped = check(staged, GATES[0], sample_rows=2)

    unique = next(g for g in report.gates if g.gate == UNIQUE_GATE)
    assert (unique.violations, len(unique.sample)) == (distinct_games, 5)
    assert all(s["n"] == 2 for s in unique.sample)
    assert (capped.violations, len(capped.sample)) == (distinct_games, 2)


def test_gate_failure_message_names_each_failing_gate_with_its_count() -> None:
    results = [GateResult("a", 2, [{"k": 1}]), GateResult("b", 0, []), GateResult("c", 1, [])]

    failure = GateFailure(results)

    assert str(failure) == "quality gates failed: a (2 violations), c (1 violations)"
    assert failure.results is results
    assert [r.ok for r in results] == [False, True, False]


def test_shipped_gates_are_sorted_unique_and_named_after_a_group() -> None:
    gates = shipped_gates()
    names = [g.name for g in gates]
    groups = {g.__name__.rsplit(".", 1)[-1] for g in GROUPS}

    assert names == sorted(set(names))
    assert all(name.split("_", 1)[0] in groups for name in names)
    assert {g.name for g in shipped_gates("games_")} <= set(names)


def test_every_shipped_model_has_exactly_one_sql_or_seed_file() -> None:
    sql = {p.stem for p in (SQL_DIR / "models").glob("*.sql")}
    seeds = {p.stem for p in (SQL_DIR / "seed").glob("*.csv")}

    assert sql == {m.name for m in MODELS if m.kind is not Kind.SEED}
    assert seeds == {m.name for m in MODELS if m.kind is Kind.SEED}
    assert [s.model for s in shipped_steps()] == list(MODELS)
    assert all(m.qualified == f'lake."nba"."{m.name}"' for m in MODELS)


def test_seed_steps_read_their_csv_with_na_as_null(root: Root, tmp_path: Path) -> None:
    csv = tmp_path / "it's.csv"
    csv.write_text("team_id,code\n1,A\n2,NA\n3,\n", encoding="utf-8")
    con = connect(root)
    con.execute('CREATE SCHEMA IF NOT EXISTS lake."nba"')
    seed = Step(Model("codes", kind=Kind.SEED, sort=("team_id",)), seed_sql(csv))

    assert build(con, seed) == 3
    assert con.execute("SELECT team_id, code FROM nba.codes").fetchall() == [
        (1, "A"),
        (2, None),
        (3, None),
    ]
    con.close()


def test_shipped_plan_builds_on_empty_staged_tables_and_every_gate_passes(root: Root) -> None:
    con = empty_lake(root)
    seeds = {m.name for m in MODELS if m.kind is Kind.SEED}

    report = curate(con, run_id="empty")

    assert set(report.rows) == {m.name for m in MODELS}
    views = {m.name for m in MODELS if m.kind is Kind.VIEW}
    assert all(report.rows[m] is None for m in views)
    assert all(n == 0 for m, n in report.rows.items() if m not in seeds | views)
    assert all((report.rows[m] or 0) > 0 for m in seeds)
    assert [g.gate for g in report.gates] == [g.name for g in shipped_gates()]
    assert all(g.ok for g in report.gates)
    for model in MODELS:
        names = list(columns(con, model.qualified))
        assert len(names) == len(set(names)), model.name
        assert model.partition is None or model.partition in names
        assert set(model.sort) <= set(names)
    con.close()


def test_build_and_check_leave_no_pending_result_on_the_connection(
    staged: duckdb.DuckDBPyConnection,
) -> None:
    staged.execute('CREATE SCHEMA IF NOT EXISTS lake."nba"')
    build(staged, STEPS[0])
    check(staged, GATES[0])

    staged.register("probe", pa.table({"x": [1]}))
    assert staged.sql("SELECT x FROM probe").fetchall() == [(1,)]


def test_insert_keeps_columns_that_only_later_rows_carry(root: Root) -> None:
    con = empty_lake(root, ["bref.player_totals"])

    insert(con, "bref.player_totals", [{"player_id": "a", "orb": 1}, {"player_id": "b", "mp": 2}])

    assert con.execute(
        "SELECT player_id, orb, mp FROM bref.player_totals ORDER BY 1"
    ).fetchall() == [("a", 1, None), ("b", None, 2)]
    con.close()


def test_building_a_view_executes_nothing(root: Root) -> None:
    con = connect(root, schemas=("nba",))
    view = Step(Model("never_read", kind=Kind.VIEW), "SELECT error('scanned') AS x")

    assert build(con, view) is None
    with pytest.raises(duckdb.InvalidInputException, match="scanned"):
        con.execute("SELECT * FROM nba.never_read").fetchall()
    con.close()


def catalog_rows(con: duckdb.DuckDBPyConnection) -> dict[str, tuple]:
    return {
        f"{s}.{n}": (k, r, lo, hi)
        for s, n, k, r, lo, hi in con.execute(
            "SELECT schema, name, kind, rows, season_min, season_max FROM meta.catalog"
        ).fetchall()
    }


def test_curate_writes_the_catalog_for_curated_and_staged_tables(
    staged: duckdb.DuckDBPyConnection,
) -> None:
    curate(staged, steps=STEPS, gates=GATES, run_id="r1")

    seasons = sorted({g["season"] for g in GAMES})
    found = catalog_rows(staged)
    assert found["nba.games"] == ("table", len(GAMES), seasons[0], seasons[-1])
    assert found["sdv.nba_stats_schedules"] == ("staged", len(GAMES), seasons[0], seasons[-1])
    profiled = staged.execute(
        "SELECT column_name, null_percent FROM meta.catalog_columns "
        "WHERE schema = 'nba' AND name = 'games' ORDER BY ordinal"
    ).fetchall()
    assert [c for c, _ in profiled] == list(columns(staged, GAMES_TABLE))
    assert dict(profiled)["game_id"] == 0


def test_failed_gate_keeps_the_previous_catalog(staged: duckdb.DuckDBPyConnection) -> None:
    curate(staged, steps=STEPS, gates=GATES, run_id="r1")
    before = catalog_rows(staged)
    duplicate_game(staged, DUPLICATED)

    with pytest.raises(GateFailure):
        curate(staged, steps=STEPS, gates=GATES, run_id="r2")

    assert catalog_rows(staged)["nba.games"] == before["nba.games"]


@pytest.mark.parametrize("fails", [False, True], ids=["pass", "gate-failure"])
def test_one_curate_records_every_gate_result_in_one_snapshot_and_one_file(
    root: Root, fails: bool
) -> None:
    con = connect(root, schemas=("t", "nba"))
    con.execute("CREATE TABLE t.x AS SELECT 1 AS i")
    gates = [Gate(f"g{n}", "SELECT 1 AS x WHERE false") for n in range(3)]
    if fails:
        gates.append(Gate("g_fails", "SELECT 1 AS x"))
    step = Step(Model("m", kind=Kind.TABLE), "SELECT i FROM t.x")

    def snapshots() -> int:
        return int(con.execute("SELECT count(*) FROM ducklake_snapshots('lake')").fetchall()[0][0])

    before = snapshots()
    if fails:
        with pytest.raises(GateFailure):
            curate(con, run_id="r", steps=[step], gates=gates)
    else:
        curate(con, run_id="r", steps=[step], gates=gates)

    files = con.execute(
        "SELECT count(*) FROM ducklake_list_files('lake', 'gate_results', schema => 'meta')"
    ).fetchall()
    recorded = con.execute("SELECT gate FROM meta.gate_results ORDER BY gate").fetchall()
    assert files == [(1,)]
    assert recorded == [(g.name,) for g in sorted(gates, key=lambda g: g.name)]
    assert snapshots() - before == (1 if fails else 2)
    con.close()


def test_a_built_table_takes_its_model_sort_order_and_no_partition(root: Root) -> None:
    con = connect(root, schemas=("nba",))
    step = Step(Model("m", kind=Kind.TABLE, sort=("season", "i")), "SELECT 1 AS i, 2 AS season")

    build(con, step)

    assert layout(con, "nba", "m") == Layout(None, ("season", "i"))
    con.close()


WINDOWED = "SELECT k, i, sum(i) OVER (PARTITION BY k ORDER BY i) AS running FROM t.x"


def chunk_lake(root: Root, keys: list[object]) -> duckdb.DuckDBPyConnection:
    con = connect(root, schemas=("t", "nba"))
    kind = "VARCHAR" if any(isinstance(k, str) for k in keys) else "BIGINT"
    con.execute(f"CREATE TABLE t.x (k {kind}, i BIGINT, _unit VARCHAR, _sha256 VARCHAR)")
    for n, key in enumerate(keys):
        stage_unit(con, f"u{n}", [(key, n), (key, n + 10)])
    return con


def stage_unit(con: duckdb.DuckDBPyConnection, unit: str, rows: list[tuple[object, int]]) -> None:
    """Replaces one unit of t.x and its meta.staged_units row, as stage does."""
    sha = f"{unit}-{len(rows)}-{sum(i for _, i in rows)}"
    with transaction(con):
        con.execute("DELETE FROM t.x WHERE _unit = ?", [unit])
        con.execute("DELETE FROM lake.meta.staged_units WHERE dataset = 't.x' AND unit = ?", [unit])
        for key, i in rows:
            con.execute("INSERT INTO t.x VALUES (?, ?, ?, ?)", [key, i, unit, sha])
        con.execute(
            "INSERT INTO lake.meta.staged_units VALUES ('t.x', ?, ?, '', ?, now())",
            [unit, sha, len(rows)],
        )


def chunked(name: str) -> Step:
    return Step(Model(name, sort=("k", "i"), chunk=Chunk("k", "t.x")), WINDOWED)


@pytest.mark.parametrize(
    "keys", [[2001, 2002, 2003, None], ["a", "it's", "b"]], ids=["integer", "string"]
)
def test_a_chunked_build_equals_the_unchunked_build_and_writes_one_file_per_chunk(
    root: Root, keys: list[object]
) -> None:
    con = chunk_lake(root, keys)
    con.execute("SET memory_limit = '1GB'")
    con.execute("SET max_temp_directory_size = '0KB'")

    with transaction(con):
        whole = build(con, Step(Model("whole", sort=("k", "i")), WINDOWED))
        parts = build(con, chunked("parts"))

    assert parts == whole == 2 * len(keys)
    every = "SELECT k, i, running FROM nba.{} ORDER BY ALL"
    assert (
        con.execute(every.format("parts")).fetchall()
        == con.execute(every.format("whole")).fetchall()
    )
    files = con.execute(
        "SELECT count(*) FROM ducklake_list_files('lake', 'parts', schema => 'nba')"
    ).fetchall()
    assert files == [(len(keys),)]
    con.close()


def test_a_failed_gate_rolls_back_every_chunk(root: Root) -> None:
    con = chunk_lake(root, [2001, 2002])
    curate(con, run_id="r1", steps=[chunked("parts")], gates=[])
    stage_unit(con, "u9", [(2003, 99)])

    with pytest.raises(GateFailure):
        curate(con, run_id="r2", steps=[chunked("parts")], gates=[Gate("fails", "SELECT 1 AS x")])

    assert con.execute("SELECT DISTINCT k FROM nba.parts ORDER BY k").fetchall() == [
        (2001,),
        (2002,),
    ]
    con.close()


def test_a_chunk_value_that_is_not_an_integer_or_a_string_is_rejected(root: Root) -> None:
    con = connect(root, schemas=("t", "nba"))
    con.execute("CREATE TABLE t.x AS SELECT DATE '2020-01-01' AS k, 1 AS i, 'u' AS _unit")

    with pytest.raises(TypeError, match="integer or a string"):
        build(con, chunked("parts"))
    con.close()


def test_no_curated_view_computes_a_window_or_qualify() -> None:
    for s in shipped_steps():
        if s.model.kind is Kind.VIEW:
            assert not re.search(r"\b(over|qualify|window)\b", s.sql, re.IGNORECASE), s.model.name


def test_every_shipped_chunk_source_is_a_staged_table_with_the_chunk_column() -> None:
    chunked = [m for m in MODELS if m.chunk]
    assert {m.name for m in chunked} == {"pbp_actors", "pbp_qualifiers", "pbp"}
    for m in chunked:
        assert m.chunk is not None
        assert m.chunk.column in {c for c, _ in STAGED[m.chunk.source]}, m.name


def test_a_curate_that_skips_a_model_keeps_its_profile_without_scanning_it(
    root: Root, monkeypatch: pytest.MonkeyPatch
) -> None:
    con = connect(root, schemas=("t", "nba"))
    con.execute("CREATE TABLE t.x AS SELECT range AS i FROM range(5)")
    step = Step(Model("m", sort=("i",)), "SELECT i FROM t.x")
    curate(con, run_id="r1", steps=[step], gates=[])
    profiled = (
        "SELECT * EXCLUDE (profiled_at) FROM meta.catalog WHERE name = 'm'",
        "SELECT * FROM meta.catalog_columns WHERE name = 'm' ORDER BY ordinal",
    )
    before = [con.execute(q).fetchall() for q in profiled]
    scanned: list[str] = []
    real = profile_module._column_stats

    def counted(c: duckdb.DuckDBPyConnection, rel: profile_module.Relation) -> list:
        scanned.append(rel.name)
        return real(c, rel)

    monkeypatch.setattr(profile_module, "_column_stats", counted)

    skipped = curate(con, run_id="r2", steps=[step], gates=[])
    after = [con.execute(q).fetchall() for q in profiled]
    rebuilt = curate(con, run_id="r3", steps=[step], gates=[], rebuild=True)

    assert skipped.skipped == ["m"] and after == before
    assert rebuilt.rows == {"m": 5}
    assert scanned == ["m"]
    con.close()


def test_the_catalog_names_each_models_sources_and_the_gates_that_read_it(
    staged: duckdb.DuckDBPyConnection,
) -> None:
    curate(staged, steps=STEPS, gates=GATES, run_id="r1")

    lineage = dict(
        (
            (n, (tuple(s), tuple(g)))
            for n, s, g in staged.execute(
                "SELECT schema || '.' || name, sources, gates FROM meta.catalog"
            ).fetchall()
        )
    )
    assert lineage["nba.games"] == (
        ("sdv.nba_stats_schedules",),
        tuple(sorted(g.name for g in GATES)),
    )
    assert lineage["sdv.nba_stats_schedules"] == ((), ())


def curated_relations(con: duckdb.DuckDBPyConnection) -> list[str]:
    return sorted(
        n
        for (n,) in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE database_name = 'lake' "
            "AND schema_name = 'nba' UNION ALL SELECT view_name FROM duckdb_views() "
            "WHERE database_name = 'lake' AND schema_name = 'nba'"
        ).fetchall()
    )


def retiring_lake(root: Root) -> tuple[duckdb.DuckDBPyConnection, Step]:
    con = connect(root, schemas=("t", "nba"))
    con.execute("CREATE TABLE t.x AS SELECT range AS i FROM range(5)")
    keep = Step(Model("keep"), "SELECT i FROM t.x")
    gone = Step(Model("gone"), "SELECT i FROM t.x")
    gone_view = Step(Model("gone_view", kind=Kind.VIEW), "SELECT i FROM t.x")
    curate(con, run_id="r1", steps=[keep, gone, gone_view], gates=[])
    return con, keep


def test_curate_with_a_registry_drops_curated_relations_no_model_registers(root: Root) -> None:
    con, keep = retiring_lake(root)

    report = curate(con, run_id="r2", steps=[keep], gates=[], registry=[keep.model])

    assert report.retired == ["gone", "gone_view"]
    assert curated_relations(con) == ["keep"]
    assert con.execute("SELECT DISTINCT model FROM meta.fingerprints").fetchall() == [("keep",)]
    assert con.execute("SELECT name FROM meta.catalog WHERE schema = 'nba'").fetchall() == [
        ("keep",)
    ]
    assert curate(con, run_id="r3", steps=[keep], gates=[], registry=[keep.model]).retired == []
    con.close()


def test_curate_without_a_registry_keeps_curated_relations_it_was_not_given(root: Root) -> None:
    con, keep = retiring_lake(root)

    report = curate(con, run_id="r2", steps=[keep], gates=[])

    assert report.retired == []
    assert curated_relations(con) == ["gone", "gone_view", "keep"]
    con.close()
