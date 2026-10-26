from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from nbalake import fingerprint as fpr
from nbalake.capture import capture
from nbalake.curate import (
    CurateReport,
    Gate,
    GateFailure,
    Step,
    curate,
    seed_sql,
    shipped_steps,
)
from nbalake.lake import Root, connect, transaction
from nbalake.models import Chunk, Kind, Model
from nbalake.stage import stage
from tests.conftest import FakeUpstream, dataset, parquet_bytes

A = Step(Model("a", sort=("k", "i")), "SELECT k, i FROM t.x")
B = Step(Model("b"), "SELECT count(*) AS n FROM nba.a")
C = Step(Model("c", sort=("i",)), "SELECT i FROM t.y")
V = Step(Model("v", kind=Kind.VIEW), "SELECT * FROM nba.c")
P = Step(
    Model("p", sort=("k", "i"), chunk=Chunk("k", "t.x")),
    "SELECT k, i, sum(i) OVER (PARTITION BY k ORDER BY i) AS running FROM t.x",
)
PLAN = (A, B, C, V)


@pytest.fixture
def con(root: Root) -> Iterator[duckdb.DuckDBPyConnection]:
    con = connect(root, schemas=("t", "nba"))
    for table in ("x", "y"):
        con.execute(f"CREATE TABLE t.{table} (k BIGINT, i BIGINT, _unit VARCHAR, _sha256 VARCHAR)")
    for n, season in enumerate((2001, 2002, 2003)):
        stage_unit(con, "t.x", f"x{season}", [(season, n), (season, n + 10)])
    stage_unit(con, "t.y", "y1", [(None, 1)])
    yield con
    con.close()


def stage_unit(
    con: duckdb.DuckDBPyConnection, table: str, unit: str, rows: list[tuple[object, int]]
) -> None:
    """Replaces one unit and its meta.staged_units row in one transaction, as stage does."""
    sha = f"{unit}-{rows}"
    with transaction(con):
        drop_unit(con, table, unit)
        for key, i in rows:
            con.execute(f"INSERT INTO {table} VALUES (?, ?, ?, ?)", [key, i, unit, sha])
        con.execute(
            "INSERT INTO lake.meta.staged_units VALUES (?, ?, ?, '', ?, now())",
            [table, unit, sha, len(rows)],
        )


def drop_unit(con: duckdb.DuckDBPyConnection, table: str, unit: str) -> None:
    con.execute(f"DELETE FROM {table} WHERE _unit = ?", [unit])
    con.execute("DELETE FROM lake.meta.staged_units WHERE dataset = ? AND unit = ?", [table, unit])


def built(report: CurateReport) -> set[str]:
    return set(report.rows)


def test_a_curate_with_nothing_changed_builds_nothing(con: duckdb.DuckDBPyConnection) -> None:
    first = curate(con, run_id="r1", steps=PLAN, gates=[])

    second = curate(con, run_id="r2", steps=PLAN, gates=[])

    assert built(first) == {"a", "b", "c", "v"}
    assert second.rows == {} and second.skipped == ["a", "b", "c", "v"]


def test_changed_sql_rebuilds_the_model_and_its_dependents_only(
    con: duckdb.DuckDBPyConnection,
) -> None:
    curate(con, run_id="r1", steps=PLAN, gates=[])
    filtered = Step(A.model, "SELECT k, i FROM t.x WHERE i < 10")

    report = curate(con, run_id="r2", steps=(filtered, B, C, V), gates=[])

    assert built(report) == {"a", "b"}
    assert report.skipped == ["c", "v"]
    assert con.execute("SELECT n FROM nba.b").fetchall() == [(3,)]


@pytest.mark.parametrize("change", ["new-bytes", "restaged"])
def test_a_restaged_unit_rebuilds_the_models_that_read_it_and_their_dependents(
    con: duckdb.DuckDBPyConnection, change: str
) -> None:
    curate(con, run_id="r1", steps=PLAN, gates=[])
    rows: list[tuple[object, int]] = [(None, 2)] if change == "new-bytes" else [(None, 1)]
    stage_unit(con, "t.y", "y1", rows)

    report = curate(con, run_id="r2", steps=PLAN, gates=[])

    assert built(report) == {"c", "v"}
    assert con.execute("SELECT i FROM nba.v").fetchall() == [(rows[0][1],)]


def test_a_restaged_unit_rebuilds_only_the_chunk_its_rows_are_in(
    con: duckdb.DuckDBPyConnection,
) -> None:
    curate(con, run_id="r1", steps=(P,), gates=[])
    kept = files_of(con, "p")
    stage_unit(con, "t.x", "x2002", [(2002, 5), (2002, 6), (2002, 7)])

    report = curate(con, run_id="r2", steps=(P,), gates=[])

    assert report.chunks == {"p": 1} and report.rows == {"p": 3}
    assert con.execute("SELECT k, i, running FROM nba.p ORDER BY k, i").fetchall() == [
        (2001, 0, 0),
        (2001, 10, 10),
        (2002, 5, 5),
        (2002, 6, 11),
        (2002, 7, 18),
        (2003, 2, 2),
        (2003, 12, 14),
    ]
    assert len(kept & files_of(con, "p")) == 2


def test_a_chunk_whose_units_are_gone_loses_its_rows(con: duckdb.DuckDBPyConnection) -> None:
    curate(con, run_id="r1", steps=(P,), gates=[])
    with transaction(con):
        drop_unit(con, "t.x", "x2003")

    report = curate(con, run_id="r2", steps=(P,), gates=[])

    assert report.chunks == {"p": 0}
    assert con.execute("SELECT DISTINCT k FROM nba.p ORDER BY k").fetchall() == [
        (2001,),
        (2002,),
    ]
    assert curate(con, run_id="r3", steps=(P,), gates=[]).skipped == ["p"]


def test_rebuild_builds_every_model_whatever_its_fingerprint(
    con: duckdb.DuckDBPyConnection,
) -> None:
    curate(con, run_id="r1", steps=PLAN, gates=[])

    report = curate(con, run_id="r2", steps=PLAN, gates=[], rebuild=True)

    assert built(report) == {"a", "b", "c", "v"}


def test_a_failed_gate_publishes_no_fingerprints(con: duckdb.DuckDBPyConnection) -> None:
    curate(con, run_id="r1", steps=PLAN, gates=[])
    filtered = Step(A.model, "SELECT k, i FROM t.x WHERE i < 10")
    changed = (filtered, B, C, V)

    with pytest.raises(GateFailure):
        curate(con, run_id="r2", steps=changed, gates=[Gate("fails", "SELECT 1 AS x")])

    assert built(curate(con, run_id="r3", steps=changed, gates=[])) == {"a", "b"}


def test_a_model_that_turns_from_a_view_into_a_table_replaces_the_view(
    con: duckdb.DuckDBPyConnection,
) -> None:
    curate(con, run_id="r1", steps=PLAN, gates=[])
    as_table = Step(Model("v"), V.sql)

    report = curate(con, run_id="r2", steps=(A, B, C, as_table), gates=[])

    assert built(report) == {"v"}
    kinds = con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE schema_name = 'nba' AND table_name = 'v'"
    ).fetchall()
    assert kinds == [(1,)]


def test_a_seed_whose_csv_changes_is_rebuilt(
    con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    csv = tmp_path / "codes.csv"
    csv.write_text("code\nA\n", encoding="utf-8")
    seed = Model("codes", kind=Kind.SEED)
    curate(con, run_id="r1", steps=(Step(seed, seed_sql(csv), "one"),), gates=[])
    csv.write_text("code\nA\nB\n", encoding="utf-8")

    report = curate(con, run_id="r2", steps=(Step(seed, seed_sql(csv), "two"),), gates=[])

    assert report.rows == {"codes": 2}


def test_references_are_the_schema_qualified_tables_and_never_ctes(
    con: duckdb.DuckDBPyConnection,
) -> None:
    pbp = next(s for s in shipped_steps() if s.model.name == "pbp")

    assert fpr.references(con, pbp.sql) == (
        "nba.pbp_actors",
        "nba.pbp_qualifiers",
        "sdv.nba_stats_pbp",
    )


def test_every_shipped_model_parses_and_reads_only_known_tables(
    con: duckdb.DuckDBPyConnection,
) -> None:
    from nbalake import datasets

    staged = {d.name for d in datasets.ALL}
    names: set[str] = set()
    for s in shipped_steps():
        for ref in fpr.references(con, s.sql):
            assert ref in staged or ref.removeprefix("nba.") in names, (s.model.name, ref)
        names.add(s.model.name)


@pytest.mark.parametrize(
    ("published", "exists", "expected"),
    [
        ({}, True, fpr.Full()),
        ({("p", None): "m"}, False, fpr.Full()),
        ({("p", None): "old"}, True, fpr.Full()),
        ({("p", None): "m", ("p", "= 1"): "c1", ("p", "= 2"): "c2"}, True, fpr.Skip()),
        (
            {("p", None): "m", ("p", "= 1"): "c1", ("p", "= 2"): "old", ("p", "= 3"): "c3"},
            True,
            fpr.Chunks(rebuild=("= 2",), delete=("= 3",)),
        ),
    ],
    ids=["unpublished", "missing", "model-changed", "unchanged", "one-chunk-changed"],
)
def test_plan_rebuilds_what_differs_from_the_published_fingerprints(
    published: fpr.Published, exists: bool, expected: fpr.Plan
) -> None:
    fp = fpr.Fingerprint("m", {"= 1": "c1", "= 2": "c2"})

    assert fpr.plan("p", fp, published, exists) == expected


def files_of(con: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    rows = con.execute(
        "SELECT data_file FROM ducklake_list_files('lake', ?, schema => 'nba')", [table]
    ).fetchall()
    return {r[0] for r in rows}


Q = Step(
    Model("q", sort=("k", "i"), chunk=Chunk("k", "t.x")),
    "SELECT p.k, p.i, p.running, y.i AS y_i FROM nba.p p LEFT JOIN t.y y ON y.k = p.k",
)


def test_a_chunked_model_reading_a_chunked_model_rebuilds_only_the_matching_chunk(
    con: duckdb.DuckDBPyConnection,
) -> None:
    curate(con, run_id="r1", steps=(P, Q), gates=[])
    stage_unit(con, "t.x", "x2002", [(2002, 5)])

    report = curate(con, run_id="r2", steps=(P, Q), gates=[])

    assert report.chunks == {"p": 1, "q": 1}
    assert con.execute("SELECT k, i FROM nba.q ORDER BY k, i").fetchall() == [
        (2001, 0),
        (2001, 10),
        (2002, 5),
        (2003, 2),
        (2003, 12),
    ]


def test_a_staged_input_with_the_chunk_column_rebuilds_only_its_chunks(
    con: duckdb.DuckDBPyConnection,
) -> None:
    curate(con, run_id="r1", steps=(P, Q), gates=[])
    stage_unit(con, "t.y", "y1", [(2003, 7)])

    report = curate(con, run_id="r2", steps=(P, Q), gates=[])

    assert report.chunks == {"q": 1} and report.skipped == ["p"]
    assert con.execute("SELECT k, y_i FROM nba.q WHERE y_i IS NOT NULL").fetchall() == [
        (2003, 7),
        (2003, 7),
    ]


def test_an_unchunked_input_change_rebuilds_every_chunk(con: duckdb.DuckDBPyConnection) -> None:
    joined = Step(
        Model("j", sort=("k", "i"), chunk=Chunk("k", "t.x")),
        "SELECT p.k, p.i, (SELECT max(i) FROM nba.c) AS c_max FROM nba.p p",
    )
    curate(con, run_id="r1", steps=(C, P, joined), gates=[])
    stage_unit(con, "t.y", "y1", [(None, 3)])

    report = curate(con, run_id="r2", steps=(C, P, joined), gates=[])

    assert report.chunks == {"j": 3} and set(report.skipped) == {"p"}


BY_SEASON = Step(
    Model("by_season", sort=("season", "game_id"), chunk=Chunk("season", "t.parts")),
    "SELECT season, game_id, pts FROM t.parts",
)


def staged_parts(root: Root, upstream: FakeUpstream, updated_at: str = "2026-10-01T00:00:00Z"):
    for season in (2020, 2021):
        rows = [{"game_id": f"{season}{i}", "pts": i + len(updated_at)} for i in range(3)]
        upstream.add_release_asset(
            "o/r", "tag", f"part_{season}.parquet", parquet_bytes(rows), updated_at
        )
    capture(root, [dataset()], client=upstream.client, index=upstream.index)


def test_fingerprinting_a_chunked_model_reads_no_data_file_of_its_staged_source(
    tmp_path: Path, upstream: FakeUpstream
) -> None:
    """The source's data files are moved away, so a scan of them would raise."""
    root = Root(tmp_path / "lake")
    con = connect(root, schemas=("t", "nba"))
    staged_parts(root, upstream)
    stage(root, con, [dataset()])

    def chunks() -> dict[str, str]:
        return fpr.fingerprint(
            con, BY_SEASON.model, BY_SEASON.sql, "", fpr.staged_units(con), {}
        ).chunks

    data = root.data / "t" / "parts"
    moved = tmp_path / "moved"
    data.rename(moved)
    try:
        recorded = chunks()
    finally:
        moved.rename(data)
    con.execute("DELETE FROM lake.meta.unit_chunks")
    scanned = chunks()

    assert sorted(recorded) == ["= 2020", "= 2021"]
    assert recorded == scanned
    con.close()


def test_a_restaged_unit_rebuilds_one_chunk_from_the_recorded_values(
    tmp_path: Path, upstream: FakeUpstream
) -> None:
    root = Root(tmp_path / "lake")
    con = connect(root, schemas=("t", "nba"))
    staged_parts(root, upstream)
    stage(root, con, [dataset()])
    curate(con, run_id="r1", steps=[BY_SEASON], gates=[])
    upstream.add_release_asset(
        "o/r",
        "tag",
        "part_2021.parquet",
        parquet_bytes([{"game_id": "x", "pts": 1}]),
        "2026-10-02T00:00:00Z",
    )
    capture(root, [dataset()], client=upstream.client, index=upstream.index)
    stage(root, con, [dataset()])

    report = curate(con, run_id="r2", steps=[BY_SEASON], gates=[])

    assert report.chunks == {"by_season": 1}
    assert con.execute("SELECT season, game_id FROM nba.by_season ORDER BY ALL").fetchall() == [
        (2020, "20200"),
        (2020, "20201"),
        (2020, "20202"),
        (2021, "x"),
    ]
    con.close()
