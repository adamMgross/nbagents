from __future__ import annotations

import os
import signal
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from nbalake.lake import (
    CAPS,
    PARQUET_OPTIONS,
    Root,
    WriterBusy,
    columns,
    connect,
    run,
    table_exists,
    transaction,
    utcnow,
    writer_lock,
)

META_TABLES = ("runs", "staged_units", "gate_results", "fingerprints")
ROW_GROUP_ROWS = 122880


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("NBALAKE_ROOT", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return home


@pytest.fixture
def opened() -> Iterator[list[duckdb.DuckDBPyConnection]]:
    cons: list[duckdb.DuckDBPyConnection] = []
    yield cons
    for c in cons:
        c.close()


def lake_schemas(con: duckdb.DuckDBPyConnection) -> set[str]:
    rows = con.execute(
        "SELECT schema_name FROM duckdb_schemas() WHERE database_name = 'lake'"
    ).fetchall()
    return {s for (s,) in rows}


def lake_options(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    rows = con.execute(
        "SELECT option_name, value FROM lake.options() WHERE scope = 'GLOBAL'"
    ).fetchall()
    return dict(rows)


def snapshot_count(con: duckdb.DuckDBPyConnection) -> int:
    row = con.execute("SELECT count(*) FROM lake.snapshots()").fetchone()
    assert row is not None
    return int(row[0])


def table_count(con: duckdb.DuckDBPyConnection, schema: str) -> int:
    row = con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE database_name = 'lake' AND schema_name = ?",
        [schema],
    ).fetchone()
    assert row is not None
    return int(row[0])


def parquet_files(root: Root) -> list[str]:
    return sorted(str(p) for p in root.data.rglob("*.parquet"))


def test_resolve_explicit_override_beats_every_environment_source(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NBALAKE_ROOT", str(tmp_path / "from_env"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    assert Root.resolve(tmp_path / "explicit") == Root((tmp_path / "explicit").resolve())
    assert Root.resolve(str(tmp_path / "explicit")) == Root((tmp_path / "explicit").resolve())


def test_resolve_nbalake_root_beats_xdg_and_home(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NBALAKE_ROOT", str(tmp_path / "from_env"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    assert Root.resolve() == Root((tmp_path / "from_env").resolve())


def test_resolve_xdg_data_home_beats_home(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    assert Root.resolve() == Root(tmp_path / "xdg" / "nbalake")


def test_resolve_defaults_to_local_share_under_home(home: Path) -> None:
    assert Root.resolve() == Root(home / ".local" / "share" / "nbalake")


def test_resolve_treats_empty_environment_variables_as_unset(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NBALAKE_ROOT", "")
    monkeypatch.setenv("XDG_DATA_HOME", "")

    assert Root.resolve() == Root(home / ".local" / "share" / "nbalake")


def test_resolve_expands_tilde_and_makes_override_and_env_absolute(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert Root.resolve("~/lake") == Root(home / "lake")
    assert Root.resolve("relative") == Root(tmp_path.resolve() / "relative")
    monkeypatch.setenv("NBALAKE_ROOT", "~/env_lake")
    assert Root.resolve() == Root(home / "env_lake")


def test_root_paths_hang_off_the_lake_directory(tmp_path: Path) -> None:
    root = Root(tmp_path / "lake")
    sha = "ab" + "0" * 62

    assert root.raw == root.path / "raw"
    assert root.blobs == root.raw / "blobs"
    assert root.fetches == root.raw / "fetches.jsonl"
    assert root.tmp == root.path / "tmp"
    assert root.spill == root.tmp / "duckdb"
    assert root.data == root.path / "data"
    assert root.catalog == root.path / "catalog.sqlite"
    assert root.writer_lock == root.path / "writer.lock"
    assert root.blob(sha) == root.blobs / "ab" / sha


def test_connect_on_a_fresh_root_lays_out_directories_catalog_options_and_schemas(
    root: Root, opened: list[duckdb.DuckDBPyConnection]
) -> None:
    con = connect(root, schemas=("t", "u"))
    opened.append(con)

    assert root.blobs.is_dir() and root.tmp.is_dir() and root.data.is_dir()
    assert root.catalog.is_file()
    catalog = sqlite3.connect(root.catalog)
    try:
        assert catalog.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    finally:
        catalog.close()
    options = lake_options(con)
    assert options["parquet_compression"] == "zstd"
    assert options["parquet_row_group_size"] == str(ROW_GROUP_ROWS)
    assert options["data_inlining_row_limit"] == "0"
    assert options["target_file_size"] == "128000000"
    assert {"meta", "t", "u"} <= lake_schemas(con)
    assert all(table_exists(con, "meta", t) for t in META_TABLES)
    assert columns(con, "lake.meta.runs") == {
        "run_id": "VARCHAR",
        "command": "VARCHAR",
        "started_at": "TIMESTAMP",
        "finished_at": "TIMESTAMP",
        "ok": "BOOLEAN",
        "detail": "VARCHAR",
    }


def test_connect_read_only_on_a_missing_root_raises_and_creates_nothing(root: Root) -> None:
    with pytest.raises(FileNotFoundError):
        connect(root, read_only=True)

    assert not root.path.exists()


def test_connect_read_only_on_an_existing_lake_reads_but_rejects_writes_and_new_schemas(
    root: Root, opened: list[duckdb.DuckDBPyConnection]
) -> None:
    writer = connect(root, schemas=("t",))
    opened.append(writer)
    writer.execute("CREATE TABLE lake.t.x AS SELECT 1 AS i")
    before = snapshot_count(writer)

    reader = connect(root, read_only=True, schemas=("later",))
    opened.append(reader)

    assert reader.execute("SELECT i FROM lake.t.x").fetchall() == [(1,)]
    with pytest.raises(duckdb.Error):
        reader.execute("INSERT INTO lake.t.x VALUES (2)")
    assert "later" not in lake_schemas(reader)
    assert snapshot_count(reader) == before


def rendered(setting: str, value: str) -> str:
    con = duckdb.connect()
    try:
        con.execute(f"SET {setting} = ?", [value])
        return str(con.execute(f"SELECT current_setting('{setting}')").fetchall()[0][0])
    finally:
        con.close()


def test_writer_and_reader_sessions_cap_memory_and_spill_under_the_lake_tmp(
    root: Root, opened: list[duckdb.DuckDBPyConnection]
) -> None:
    writer = connect(root)
    opened.append(writer)
    reader = connect(root, read_only=True)
    opened.append(reader)

    for con in (writer, reader):
        settings = con.execute(
            "SELECT current_setting('memory_limit'), current_setting('max_temp_directory_size'), "
            "current_setting('temp_directory')"
        ).fetchall()[0]
        assert settings == (
            rendered("memory_limit", CAPS.memory),
            rendered("max_temp_directory_size", CAPS.spill),
            str(root.spill),
        )


def test_a_spilling_session_writes_under_the_lake_tmp_and_not_the_working_directory(
    root: Root,
    opened: list[duckdb.DuckDBPyConnection],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    con = connect(root)
    opened.append(con)
    con.execute("SET memory_limit = '32MB'")
    con.execute("SET threads = 1")

    con.execute(
        "SELECT i FROM (SELECT (random() * 1e9)::BIGINT AS i, repeat('x', 40) AS s "
        "FROM range(3000000)) ORDER BY s, i OFFSET 2999999"
    ).fetchall()

    assert any(root.spill.iterdir())
    assert not any(cwd.iterdir())


def test_a_writer_sets_an_option_an_older_lake_lacks_once_and_a_reader_never(
    root: Root, opened: list[duckdb.DuckDBPyConnection], monkeypatch: pytest.MonkeyPatch
) -> None:
    with monkeypatch.context() as older:
        older.delitem(PARQUET_OPTIONS, "target_file_size")
        opened.append(connect(root))
    assert "target_file_size" not in lake_options(opened[0])

    reader = connect(root, read_only=True)
    opened.append(reader)
    assert "target_file_size" not in lake_options(reader)
    writer = connect(root)
    opened.append(writer)
    after_fill = snapshot_count(writer)
    again = connect(root)
    opened.append(again)

    assert lake_options(again)["target_file_size"] == "128000000"
    assert snapshot_count(again) == after_fill


def test_second_connect_on_the_same_root_adds_no_snapshots(
    root: Root, opened: list[duckdb.DuckDBPyConnection]
) -> None:
    first = connect(root, schemas=("t",))
    opened.append(first)
    before = snapshot_count(first)

    second = connect(root, schemas=("t",))
    opened.append(second)

    assert snapshot_count(second) == before
    assert snapshot_count(first) == before
    assert lake_options(second) == lake_options(first)


def test_transaction_rolls_back_on_exception_and_leaves_the_connection_usable(
    con: duckdb.DuckDBPyConnection,
) -> None:
    before = table_count(con, "t")

    with pytest.raises(RuntimeError, match="boom"), transaction(con):
        con.execute("CREATE TABLE lake.t.rolled (x INTEGER)")
        raise RuntimeError("boom")
    assert table_count(con, "t") == before
    assert not table_exists(con, "t", "rolled")

    with pytest.raises(duckdb.CatalogException), transaction(con):
        con.execute("CREATE TABLE lake.t.half (x INTEGER)")
        con.execute("SELECT * FROM lake.t.does_not_exist")
    assert not table_exists(con, "t", "half")

    with transaction(con):
        con.execute("CREATE TABLE lake.t.after (x INTEGER)")
    assert table_exists(con, "t", "after")


def test_transaction_commits_on_normal_exit_and_is_visible_to_a_new_connection(
    root: Root, con: duckdb.DuckDBPyConnection, opened: list[duckdb.DuckDBPyConnection]
) -> None:
    with transaction(con):
        con.execute("CREATE TABLE lake.t.kept (x INTEGER)")
        con.execute("INSERT INTO lake.t.kept VALUES (7)")

    other = connect(root, schemas=("t",))
    opened.append(other)
    assert other.execute("SELECT x FROM lake.t.kept").fetchall() == [(7,)]


def test_run_records_success_with_empty_detail(con: duckdb.DuckDBPyConnection) -> None:
    with run(con, "stage") as run_id:
        pass

    rows = con.execute(
        "SELECT run_id, command, ok, detail, started_at <= finished_at FROM lake.meta.runs"
    ).fetchall()
    assert rows == [(run_id, "stage", True, "", True)]
    assert isinstance(run_id, str) and run_id


def test_run_records_failure_with_exception_text_and_reraises(
    con: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(ValueError, match="nope"), run(con, "curate") as run_id:
        raise ValueError("nope")

    rows = con.execute("SELECT run_id, command, ok, detail FROM lake.meta.runs").fetchall()
    assert rows == [(run_id, "curate", False, "ValueError: nope")]


def test_run_records_an_interrupted_run_before_propagating(
    con: duckdb.DuckDBPyConnection,
) -> None:
    with pytest.raises(KeyboardInterrupt), run(con, "refresh"):
        raise KeyboardInterrupt

    ((command, ok, detail),) = con.execute(
        "SELECT command, ok, detail FROM lake.meta.runs"
    ).fetchall()
    assert (command, ok) == ("refresh", False)
    assert detail.startswith("KeyboardInterrupt")


def test_table_exists_is_scoped_to_schema_and_lake(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE TABLE lake.t.present (i INTEGER)")
    con.execute("CREATE TEMP TABLE scratch (i INTEGER)")

    assert table_exists(con, "t", "present")
    assert not table_exists(con, "t", "absent")
    assert not table_exists(con, "meta", "present")
    assert not table_exists(con, "main", "scratch")
    assert not table_exists(con, "temp", "scratch")


def test_columns_returns_declared_order_and_types_and_raises_on_absent_table(
    con: duckdb.DuckDBPyConnection,
) -> None:
    con.execute("CREATE TABLE lake.t.typed (z BIGINT, a VARCHAR, m DOUBLE, b BOOLEAN)")

    assert list(columns(con, 'lake."t"."typed"').items()) == [
        ("z", "BIGINT"),
        ("a", "VARCHAR"),
        ("m", "DOUBLE"),
        ("b", "BOOLEAN"),
    ]
    with pytest.raises(duckdb.CatalogException):
        columns(con, 'lake."t"."absent"')


def test_lake_tables_are_plain_zstd_parquet_with_bounded_row_groups(
    root: Root, con: duckdb.DuckDBPyConnection
) -> None:
    con.execute("CREATE TABLE lake.t.big (i BIGINT, s VARCHAR)")
    con.execute("INSERT INTO lake.t.big SELECT range, 'v' || range::VARCHAR FROM range(300000)")

    files = parquet_files(root)
    plain = duckdb.connect()
    try:
        totals = plain.execute("SELECT count(*), sum(i) FROM read_parquet(?)", [files]).fetchone()
        compressions = {
            c
            for (c,) in plain.execute(
                "SELECT compression FROM parquet_metadata(?)", [files]
            ).fetchall()
        }
        row_groups = [
            n
            for (n,) in plain.execute(
                "SELECT row_group_num_rows FROM parquet_metadata(?) "
                "GROUP BY file_name, row_group_id, row_group_num_rows",
                [files],
            ).fetchall()
        ]
    finally:
        plain.close()
    assert totals == (300000, sum(range(300000)))
    assert compressions == {"ZSTD"}
    assert sum(row_groups) == 300000
    assert max(row_groups) == ROW_GROUP_ROWS


def test_small_inserts_land_in_parquet_files_rather_than_the_catalog(
    root: Root, con: duckdb.DuckDBPyConnection
) -> None:
    con.execute("CREATE TABLE lake.t.tiny (i INTEGER, s VARCHAR)")
    con.execute("INSERT INTO lake.t.tiny VALUES (1, 'one')")

    files = parquet_files(root)
    assert len(files) == 1
    plain = duckdb.connect()
    try:
        assert plain.execute("SELECT i, s FROM read_parquet(?)", [files]).fetchall() == [(1, "one")]
    finally:
        plain.close()


def test_utcnow_is_naive_utc() -> None:
    now = utcnow()

    assert now.tzinfo is None
    assert abs(now - datetime.now(UTC).replace(tzinfo=None)) < timedelta(minutes=1)


HOLD_LOCK = """
import sys
from pathlib import Path
from nbalake.lake import Root, writer_lock
with writer_lock(Root(Path(sys.argv[1])), "refresh"):
    print("held", flush=True)
    sys.stdin.read()
"""


def hold_in_child(root: Root) -> subprocess.Popen[str]:
    child = subprocess.Popen(
        [sys.executable, "-c", HOLD_LOCK, str(root.path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert child.stdout is not None
    assert child.stdout.readline() == "held\n"
    return child


def test_writer_lock_refuses_a_second_process_and_names_the_holder(root: Root) -> None:
    child = hold_in_child(root)
    try:
        with pytest.raises(WriterBusy) as busy, writer_lock(root, "stage"):
            pass
        assert f"pid {child.pid}" in str(busy.value)
        assert "refresh" in str(busy.value)
    finally:
        child.communicate("")

    with writer_lock(root, "stage"):
        assert root.writer_lock.read_text().startswith(f"{os.getpid()} stage ")


def test_writer_lock_is_released_when_its_holder_is_killed(root: Root) -> None:
    child = hold_in_child(root)
    child.send_signal(signal.SIGKILL)
    child.wait()

    with writer_lock(root, "curate"):
        pass


def test_writer_lock_refuses_a_second_holder_in_the_same_process(root: Root) -> None:
    with writer_lock(root, "refresh"), pytest.raises(WriterBusy), writer_lock(root, "vacuum"):
        pass
