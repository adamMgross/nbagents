from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest

from nbalake.curate import Gate, GateFailure, Step, curate
from nbalake.lake import CURATE_COMMIT, METADATA, Root, connect
from nbalake.models.model import Kind, Model
from nbalake.vacuum import catalog_size, previous_curate, vacuum

LATER = timedelta(hours=2)
MODEL = Step(Model("m", kind=Kind.TABLE), "SELECT i FROM t.x")
FAILING = Gate("always_fails", "SELECT 1 AS x")


@pytest.fixture
def con(root: Root) -> Iterator[duckdb.DuckDBPyConnection]:
    con = connect(root, schemas=("t", "nba"))
    con.execute("CREATE TABLE t.x (i BIGINT)")
    yield con
    con.close()


def small_inserts(con: duckdb.DuckDBPyConnection, values: range) -> None:
    for i in values:
        con.execute("INSERT INTO t.x VALUES (?)", [i])


def live_files(con: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    schema, name = table.split(".")
    rows = con.execute(
        "SELECT data_file FROM ducklake_list_files('lake', ?, schema => ?)", [name, schema]
    ).fetchall()
    return {Path(r[0]).name for r in rows}


def on_disk(root: Root) -> set[str]:
    return {p.name for p in root.data.rglob("*.parquet")}


def unreferenced(con: duckdb.DuckDBPyConnection, root: Root) -> set[str]:
    rows = con.execute(
        f"SELECT path FROM {METADATA}.ducklake_data_file "
        f"UNION ALL SELECT path FROM {METADATA}.ducklake_files_scheduled_for_deletion"
    ).fetchall()
    return on_disk(root) - {Path(r[0]).name for r in rows}


def run_curate(con: duckdb.DuckDBPyConnection, run_id: str) -> int:
    curate(con, run_id=run_id, steps=[MODEL], gates=[], rebuild=True)
    rows = con.execute(
        "SELECT snapshot_id FROM ducklake_snapshots('lake') WHERE commit_extra_info = ?", [run_id]
    ).fetchall()
    return int(rows[0][0])


def oldest_snapshot(con: duckdb.DuckDBPyConnection) -> int:
    return int(
        con.execute("SELECT min(snapshot_id) FROM ducklake_snapshots('lake')").fetchall()[0][0]
    )


def test_vacuum_merges_small_files_into_one_and_keeps_every_row(
    con: duckdb.DuckDBPyConnection,
) -> None:
    small_inserts(con, range(5))
    assert len(live_files(con, "t.x")) == 5

    report = vacuum(con)

    assert len(live_files(con, "t.x")) == 1
    assert con.execute("SELECT i FROM t.x ORDER BY i").fetchall() == [(i,) for i in range(5)]
    assert report.merged == 5
    assert report.after.live_files == report.before.live_files - 4


def test_curate_tags_its_commit_and_a_rolled_back_curate_tags_nothing(
    con: duckdb.DuckDBPyConnection,
) -> None:
    small_inserts(con, range(2))
    published = run_curate(con, "r1")

    with pytest.raises(GateFailure):
        curate(con, run_id="r2", steps=[MODEL], gates=[FAILING])

    tagged = con.execute(
        "SELECT snapshot_id, author, commit_extra_info FROM ducklake_snapshots('lake') "
        "WHERE commit_message = ?",
        [CURATE_COMMIT],
    ).fetchall()
    assert tagged == [(published, "nbalake", "r1")]


def test_nothing_expires_before_two_curates(con: duckdb.DuckDBPyConnection) -> None:
    small_inserts(con, range(3))
    run_curate(con, "r1")
    first = oldest_snapshot(con)

    report = vacuum(con, now=datetime.now(UTC) + LATER)

    assert previous_curate(con) is None
    assert report.expired == 0
    assert oldest_snapshot(con) == first


def test_vacuum_expires_only_snapshots_before_the_previous_curate_and_keeps_their_files(
    root: Root, con: duckdb.DuckDBPyConnection
) -> None:
    con.execute("CREATE TABLE t.gone AS SELECT 1 AS j")
    gone = live_files(con, "t.gone")
    con.execute("DROP TABLE t.gone")
    small_inserts(con, range(3))
    first = run_curate(con, "r1")
    retained = live_files(con, "t.x") | live_files(con, "nba.m")
    con.execute("DELETE FROM t.x")
    small_inserts(con, range(10, 12))
    run_curate(con, "r2")
    older = con.execute(
        "SELECT count(*) FROM ducklake_snapshots('lake') WHERE snapshot_id < ?", [first]
    ).fetchall()[0][0]

    report = vacuum(con, now=datetime.now(UTC) + LATER)

    assert previous_curate(con) == first
    assert oldest_snapshot(con) == first
    assert report.expired == older > 0
    assert retained <= on_disk(root)
    assert not gone & on_disk(root)
    for table in ("t.x", "nba.m"):
        at_first = con.execute(f"SELECT i FROM {table} AT (VERSION => {first}) ORDER BY i")
        assert at_first.fetchall() == [(0,), (1,), (2,)]
    assert con.execute("SELECT i FROM nba.m ORDER BY i").fetchall() == [(10,), (11,)]
    with pytest.raises(duckdb.Error):
        con.execute(f"SELECT * FROM t.x AT (VERSION => {first - 1})").fetchall()


def test_a_reader_mid_transaction_keeps_reading_through_a_vacuum_and_files_go_an_hour_later(
    root: Root, con: duckdb.DuckDBPyConnection
) -> None:
    small_inserts(con, range(4))
    merged_away = live_files(con, "t.x")
    reader = connect(root, read_only=True)
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT sum(i) FROM t.x WHERE i >= 0").fetchall() == [(6,)]

        during = vacuum(con)

        assert reader.execute("SELECT sum(i) FROM t.x WHERE i >= 0").fetchall() == [(6,)]
        reader.execute("COMMIT")
    finally:
        reader.close()
    assert during.merged == 4 and during.deleted == 0
    assert merged_away <= on_disk(root)

    later = vacuum(con, now=datetime.now(UTC) + LATER)

    assert later.deleted == len(merged_away)
    assert not merged_away & on_disk(root)
    assert con.execute("SELECT sum(i) FROM t.x WHERE i >= 0").fetchall() == [(6,)]


def test_parquet_no_catalog_row_references_is_deleted_an_hour_later(
    root: Root, con: duckdb.DuckDBPyConnection
) -> None:
    """A writer killed between writing Parquet and committing leaves such a file."""
    small_inserts(con, range(3))
    stray = root.data / "t" / "x" / "ducklake-killed-writer.parquet"
    con.execute(f"COPY (SELECT 9 AS i) TO '{stray}' (FORMAT parquet)")

    vacuum(con)
    kept = unreferenced(con, root)
    vacuum(con, now=datetime.now(UTC) + LATER)

    assert kept == {stray.name}
    assert unreferenced(con, root) == set()
    assert con.execute("SELECT sum(i) FROM t.x WHERE i >= 0").fetchall() == [(3,)]


def test_catalog_size_counts_live_files_stats_rows_and_snapshots(
    con: duckdb.DuckDBPyConnection,
) -> None:
    before = catalog_size(con)

    small_inserts(con, range(2))

    after = catalog_size(con)
    assert after.live_files == before.live_files + 2
    assert after.stats_rows == before.stats_rows + 2
    assert after.snapshots == before.snapshots + 2


def test_vacuum_merges_into_one_file_in_the_table_sort_order(
    root: Root, con: duckdb.DuckDBPyConnection
) -> None:
    con.execute("ALTER TABLE t.x SET SORTED BY (i)")
    small_inserts(con, range(5, 0, -1))

    vacuum(con)

    (merged,) = live_files(con, "t.x")
    (path,) = root.data.rglob(merged)
    assert pq.read_table(path).column("i").to_pylist() == [1, 2, 3, 4, 5]
