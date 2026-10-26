from __future__ import annotations

import fcntl
import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from nbalake.runtime import Runtime


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


PARQUET_OPTIONS = {
    "parquet_compression": "zstd",
    "parquet_row_group_size": "122880",
    "data_inlining_row_limit": "0",
    "target_file_size": "128MB",
}

META_SCHEMA = "meta"
METADATA = "__ducklake_metadata_lake"
CURATE_COMMIT = "curate"


@dataclass(frozen=True, slots=True)
class Layout:
    partition: str | None
    sort: tuple[str, ...]


NO_LAYOUT = Layout(partition=None, sort=())


@dataclass(frozen=True, slots=True)
class Limits:
    memory: str
    spill: str


CAPS = Limits(memory="4GB", spill="4GB")


@dataclass(frozen=True, slots=True)
class Root:
    path: Path

    @classmethod
    def resolve(cls, override: str | os.PathLike[str] | None = None) -> Root:
        if override is not None:
            return cls(Path(override).expanduser().resolve())
        if env := os.environ.get("NBALAKE_ROOT"):
            return cls(Path(env).expanduser().resolve())
        xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        return cls(Path(xdg) / "nbalake")

    @property
    def raw(self) -> Path:
        return self.path / "raw"

    @property
    def blobs(self) -> Path:
        return self.raw / "blobs"

    @property
    def drop(self) -> Path:
        return self.path / "drop"

    @property
    def fetches(self) -> Path:
        return self.raw / "fetches.jsonl"

    @property
    def tmp(self) -> Path:
        return self.path / "tmp"

    @property
    def spill(self) -> Path:
        return self.tmp / "duckdb"

    @property
    def catalog(self) -> Path:
        return self.path / "catalog.sqlite"

    @property
    def data(self) -> Path:
        return self.path / "data"

    @property
    def writer_lock(self) -> Path:
        return self.path / "writer.lock"

    @property
    def scratch(self) -> Path:
        return self.path / "scratch.duckdb"

    def blob(self, sha256: str) -> Path:
        return self.blobs / sha256[:2] / sha256

    def ensure(self) -> None:
        for d in (self.blobs, self.tmp, self.data):
            d.mkdir(parents=True, exist_ok=True)


class WriterBusy(Exception):
    pass


@contextmanager
def writer_lock(root: Root, command: str) -> Generator[None]:
    root.path.mkdir(parents=True, exist_ok=True)
    with open(root.writer_lock, "a+", encoding="utf-8") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            f.seek(0)
            raise WriterBusy(f"another nbalake write is running: {_holder(f.read())}") from None
        f.seek(0)
        f.truncate()
        f.write(f"{os.getpid()} {command} {utcnow():%Y-%m-%dT%H:%M:%SZ}\n")
        f.flush()
        yield


def _holder(line: str) -> str:
    match line.split():
        case [pid, command, started]:
            return f"pid {pid}, {command} since {started}"
        case _:
            return "holder unknown"


def _init_catalog(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA journal_mode=WAL")
    finally:
        con.close()


def connect(
    root: Root,
    *,
    read_only: bool = False,
    schemas: tuple[str, ...] = (),
    limits: Limits = CAPS,
) -> duckdb.DuckDBPyConnection:
    fresh = not root.catalog.exists()
    if fresh and read_only:
        setup = Runtime.current().command("nbalake setup")
        raise FileNotFoundError(f"no lake at {root.path}, build one with: {setup}")
    con = duckdb.connect(config=Runtime.current().duckdb_config())
    con.execute("INSTALL ducklake; LOAD ducklake; INSTALL sqlite; LOAD sqlite;")
    if fresh:
        root.ensure()
        _init_catalog(root.catalog)
    _set_limits(con, root, limits)
    mode = ", READ_ONLY" if read_only else ""
    con.execute(f"ATTACH 'ducklake:sqlite:{root.catalog}' AS lake (DATA_PATH '{root.data}'{mode})")
    con.execute("USE lake").fetchall()
    if not read_only:
        with transaction(con):
            _set_options(con, fresh)
            for schema in (META_SCHEMA, *schemas):
                con.execute(f'CREATE SCHEMA IF NOT EXISTS lake."{schema}"')
            _ensure_meta(con)
    return con


def _set_options(con: duckdb.DuckDBPyConnection, fresh: bool) -> None:
    rows = con.execute("SELECT option_name FROM lake.options() WHERE scope = 'GLOBAL'").fetchall()
    present = {r[0] for r in rows}
    for k, v in PARQUET_OPTIONS.items():
        if fresh or k not in present:
            con.execute("CALL lake.set_option(?, ?)", [k, v])


def _set_limits(con: duckdb.DuckDBPyConnection, root: Root, limits: Limits) -> None:
    root.spill.mkdir(parents=True, exist_ok=True)
    con.execute("SET temp_directory = ?", [str(root.spill)])
    con.execute("SET memory_limit = ?", [limits.memory])
    con.execute("SET max_temp_directory_size = ?", [limits.spill])


def _ensure_meta(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS lake.meta.runs (
            run_id VARCHAR, command VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP,
            ok BOOLEAN, detail VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS lake.meta.staged_units (
            dataset VARCHAR, unit VARCHAR, sha256 VARCHAR, fetched_at VARCHAR,
            rows BIGINT, staged_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS lake.meta.unit_chunks (
            dataset VARCHAR, unit VARCHAR, sha256 VARCHAR, column_name VARCHAR, value VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS lake.meta.gate_results (
            run_id VARCHAR, gate VARCHAR, violations BIGINT, sample VARCHAR, checked_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS lake.meta.fingerprints (
            model VARCHAR, chunk VARCHAR, fingerprint VARCHAR, run_id VARCHAR
        )
        """
    )


@contextmanager
def transaction(con: duckdb.DuckDBPyConnection) -> Generator[None]:
    con.execute("BEGIN")
    try:
        yield
    except BaseException:
        con.execute("ROLLBACK")
        raise
    con.execute("COMMIT")


def table_exists(
    con: duckdb.DuckDBPyConnection, schema: str, table: str, *, database: str = "lake"
) -> bool:
    row = con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE database_name=? "
        "AND schema_name=? AND table_name=?",
        [database, schema, table],
    ).fetchone()
    return bool(row and row[0])


def layout(con: duckdb.DuckDBPyConnection, schema: str, table: str) -> Layout:
    ids = con.execute(
        f"SELECT t.table_id FROM {METADATA}.ducklake_table t "
        f"JOIN {METADATA}.ducklake_schema s USING (schema_id) "
        "WHERE t.end_snapshot IS NULL AND s.end_snapshot IS NULL "
        "AND s.schema_name = ? AND t.table_name = ?",
        [schema, table],
    ).fetchall()
    (table_id,) = ids[0]
    partition = con.execute(
        f"SELECT c.column_name FROM {METADATA}.ducklake_partition_info p "
        f"JOIN {METADATA}.ducklake_partition_column pc USING (partition_id, table_id) "
        f"JOIN {METADATA}.ducklake_column c ON c.table_id = pc.table_id "
        "AND c.column_id = pc.column_id AND c.end_snapshot IS NULL "
        "WHERE p.table_id = ? AND p.end_snapshot IS NULL ORDER BY pc.partition_key_index",
        [table_id],
    ).fetchall()
    sort = con.execute(
        f"SELECT e.expression FROM {METADATA}.ducklake_sort_info i "
        f"JOIN {METADATA}.ducklake_sort_expression e USING (sort_id, table_id) "
        "WHERE i.table_id = ? AND i.end_snapshot IS NULL ORDER BY e.sort_key_index",
        [table_id],
    ).fetchall()
    return Layout(
        partition=partition[0][0] if partition else None,
        sort=tuple(_unquote(e) for (e,) in sort),
    )


def _unquote(expression: str) -> str:
    if expression.startswith('"') and expression.endswith('"'):
        return expression[1:-1].replace('""', '"')
    return expression


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def set_layout(
    con: duckdb.DuckDBPyConnection, qualified: str, want: Layout, have: Layout = NO_LAYOUT
) -> None:
    """A partition change applies to files written after it."""
    if want.partition != have.partition:
        if want.partition:
            con.execute(f"ALTER TABLE {qualified} SET PARTITIONED BY ({quote(want.partition)})")
        else:
            con.execute(f"ALTER TABLE {qualified} RESET PARTITIONED BY")
    if want.sort != have.sort:
        if want.sort:
            keys = ", ".join(quote(c) for c in want.sort)
            con.execute(f"ALTER TABLE {qualified} SET SORTED BY ({keys})")
        else:
            con.execute(f"ALTER TABLE {qualified} RESET SORTED BY")


def columns(con: duckdb.DuckDBPyConnection, qualified: str) -> dict[str, str]:
    return {name: typ for name, typ, *_ in con.execute(f"DESCRIBE {qualified}").fetchall()}


@contextmanager
def run(con: duckdb.DuckDBPyConnection, command: str) -> Generator[str]:
    """Records one CLI invocation in meta.runs. Yields the run id."""
    from uuid import uuid4

    run_id = uuid4().hex[:12]
    started = utcnow()
    ok = False
    detail = ""
    try:
        yield run_id
        ok = True
    except BaseException as e:
        detail = f"{type(e).__name__}: {e}"
        raise
    finally:
        con.execute(
            "INSERT INTO lake.meta.runs VALUES (?, ?, ?, ?, ?, ?)",
            [run_id, command, started, utcnow(), ok, detail],
        )
