from __future__ import annotations

import shutil
import tarfile
import zipfile
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, NamedTuple
from uuid import uuid4

import duckdb

from nbalake.capture import FetchRecord, RawStore, units_in_store
from nbalake.lake import (
    META_SCHEMA,
    Layout,
    Root,
    columns,
    layout,
    quote,
    set_layout,
    table_exists,
    transaction,
    utcnow,
)
from nbalake.model import Csv, Dataset, Parquet
from nbalake.models import ALL as MODELS
from nbalake.models.model import CURATED

LINEAGE = ("_unit", "_sha256", "_fetched_at")
CHUNK_COLUMNS = tuple(sorted({m.chunk.column for m in MODELS if m.chunk}))

NUMERIC_RANK = {
    "TINYINT": 0,
    "SMALLINT": 1,
    "INTEGER": 2,
    "BIGINT": 3,
    "HUGEINT": 4,
    "FLOAT": 5,
    "DOUBLE": 6,
}

PY_TYPES: dict[type, str] = {bool: "BOOLEAN", int: "INTEGER", float: "DOUBLE", str: "VARCHAR"}

NULL_TYPES = ("NULL", '"NULL"')


class SchemaDrift(Exception):
    pass


class LayoutDrift(Exception):
    pass


def widen(have: str, want: str) -> str | None:
    if have == want or have == "VARCHAR":
        return have
    if have in NUMERIC_RANK and want in NUMERIC_RANK:
        return have if NUMERIC_RANK[have] >= NUMERIC_RANK[want] else want
    return None


@contextmanager
def materialized(root: Root, blob: Path, member: str | None) -> Generator[Path]:
    if zipfile.is_zipfile(blob):
        with zipfile.ZipFile(blob) as z:
            names = z.namelist()
            name = member or _single(names, blob)
            yield from _extract(root, name, lambda out: shutil.copyfileobj(z.open(name), out))
    elif tarfile.is_tarfile(blob):
        with tarfile.open(blob, "r:*") as t:
            names = [m.name for m in t.getmembers() if m.isfile()]
            name = member or _single(names, blob)
            src = t.extractfile(name)
            assert src is not None
            yield from _extract(root, name, lambda out: shutil.copyfileobj(src, out))
    else:
        yield blob


def _single(names: list[str], blob: Path) -> str:
    if len(names) != 1:
        raise ValueError(f"{blob.name}: archive holds {len(names)} files, name the member")
    return names[0]


def _extract(root: Root, name: str, copy: Callable[[BinaryIO], object]) -> Generator[Path]:
    root.tmp.mkdir(parents=True, exist_ok=True)
    out = root.tmp / f"{uuid4().hex}-{Path(name).name}"
    try:
        with out.open("wb") as f:
            copy(f)
        yield out
    finally:
        out.unlink(missing_ok=True)


@contextmanager
def open_source(
    con: duckdb.DuckDBPyConnection, root: Root, ds: Dataset, rec: FetchRecord
) -> Generator[str]:
    blob = root.blob(rec.sha256)
    match ds.parse:
        case Parquet():
            yield f"read_parquet('{blob}')"
        case Csv(member=member, nulls=nulls, all_varchar=all_varchar):
            with materialized(root, blob, member) as path:
                yield (
                    f"read_csv('{path}', header=true, sample_size=-1, "
                    f"nullstr={list(nulls)!r}, all_varchar={all_varchar})"
                )


def load_unit(con: duckdb.DuckDBPyConnection, ds: Dataset, rec: FetchRecord, src: str) -> int:
    src_cols = {
        name: typ
        for name, typ, *_ in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()
        if typ not in NULL_TYPES
    }
    casts = dict(ds.types)
    select = [
        (f"CAST({quote(c)} AS {casts[c]})" if c in casts else quote(c)) + f" AS {quote(c)}"
        for c in src_cols
    ]
    params: list[object] = []
    for name, value in ds.columns_for(rec.key).items():
        if name in src_cols:
            continue
        select.append(f"CAST(? AS {PY_TYPES[type(value)]}) AS {quote(name)}")
        params.append(value)
    for name, value in zip(LINEAGE, (rec.key, rec.sha256, rec.fetched_at), strict=True):
        select.append(f"CAST(? AS VARCHAR) AS {name}")
        params.append(value)
    projection = ", ".join(select)
    incoming = {
        name: typ
        for name, typ, *_ in con.execute(
            f"DESCRIBE SELECT {projection} FROM {src}", params
        ).fetchall()
    }
    if not table_exists(con, ds.schema, ds.table):
        con.execute(
            f"CREATE TABLE {ds.qualified} AS SELECT {projection} FROM {src} LIMIT 0", params
        )
        set_layout(con, ds.qualified, Layout(ds.partition, ds.sort))
    else:
        reconcile(con, ds, incoming)
    order = f" ORDER BY {', '.join(quote(c) for c in ds.sort)}" if ds.sort else ""
    row = con.execute(
        f"INSERT INTO {ds.qualified} BY NAME SELECT {projection} FROM {src}{order}", params
    ).fetchone()
    return int(row[0]) if row else 0


def drop_unit(con: duckdb.DuckDBPyConnection, ds: Dataset, unit: str, sha: str) -> None:
    con.execute(f"DELETE FROM {ds.qualified} WHERE _unit = ? AND _sha256 = ?", [unit, sha])
    for meta in ("staged_units", "unit_chunks"):
        con.execute(
            f"DELETE FROM lake.meta.{meta} WHERE dataset = ? AND unit = ? AND sha256 = ?",
            [ds.name, unit, sha],
        )


def forget_dataset(con: duckdb.DuckDBPyConnection, name: str) -> None:
    for meta in ("staged_units", "unit_chunks"):
        con.execute(f"DELETE FROM lake.{META_SCHEMA}.{meta} WHERE dataset = ?", [name])


def retire(con: duckdb.DuckDBPyConnection, registry: Iterable[Dataset]) -> list[str]:
    """Drops every staged table no registered dataset produces, with its meta rows."""
    registered = {ds.name for ds in registry}
    kept_schemas = {CURATED, META_SCHEMA} | {name.split(".", 1)[0] for name in registered}
    staged = con.execute(
        "SELECT schema_name || '.' || table_name FROM duckdb_tables() "
        "WHERE database_name = 'lake' AND schema_name NOT IN (?, ?) ORDER BY 1",
        [CURATED, META_SCHEMA],
    ).fetchall()
    retired = [name for (name,) in staged if name not in registered]
    with transaction(con):
        for name in retired:
            schema, table = name.split(".", 1)
            con.execute(f"DROP TABLE lake.{quote(schema)}.{quote(table)}")
            forget_dataset(con, name)
        empty = con.execute(
            "SELECT schema_name FROM duckdb_schemas() s WHERE database_name = 'lake' "
            "AND NOT internal AND NOT EXISTS (SELECT 1 FROM duckdb_tables() t "
            "WHERE t.database_name = 'lake' AND t.schema_name = s.schema_name) "
            "AND NOT EXISTS (SELECT 1 FROM duckdb_views() v "
            "WHERE v.database_name = 'lake' AND v.schema_name = s.schema_name)"
        ).fetchall()
        for (schema,) in empty:
            if schema not in kept_schemas and schema != "main":
                con.execute(f"DROP SCHEMA lake.{quote(schema)}")
    return retired


def chunk_columns(con: duckdb.DuckDBPyConnection, ds: Dataset) -> list[str]:
    have = columns(con, ds.qualified)
    return [c for c in CHUNK_COLUMNS if c in have]


def record_chunks(con: duckdb.DuckDBPyConnection, ds: Dataset, unit: str, sha: str) -> None:
    for column in chunk_columns(con, ds):
        con.execute(
            "INSERT INTO lake.meta.unit_chunks "
            f"SELECT DISTINCT ?, _unit, _sha256, ?, to_json({quote(column)})::VARCHAR "
            f"FROM {ds.qualified} WHERE _unit = ? AND _sha256 = ?",
            [ds.name, column, unit, sha],
        )


def backfill_chunks(con: duckdb.DuckDBPyConnection, ds: Dataset) -> int:
    """Records the chunk values of staged units with rows and none recorded, in one scan."""
    added = 0
    for column in chunk_columns(con, ds):
        missing = (
            "SELECT unit, sha256 FROM lake.meta.staged_units WHERE dataset = $dataset AND rows > 0 "
            "EXCEPT SELECT unit, sha256 FROM lake.meta.unit_chunks "
            "WHERE dataset = $dataset AND column_name = $column"
        )
        params = {"dataset": ds.name, "column": column}
        if not con.execute(f"SELECT count(*) FROM ({missing})", params).fetchall()[0][0]:
            continue
        row = con.execute(
            f"INSERT INTO lake.meta.unit_chunks WITH missing AS ({missing}) "
            f"SELECT DISTINCT $dataset, t._unit, t._sha256, $column, "
            f"to_json(t.{quote(column)})::VARCHAR FROM {ds.qualified} t "
            "SEMI JOIN missing m ON m.unit = t._unit AND m.sha256 = t._sha256",
            params,
        ).fetchall()
        added += int(row[0][0])
    return added


def align_layout(con: duckdb.DuckDBPyConnection, ds: Dataset) -> None:
    """Sets a changed sort order. A changed partition raises, since old files keep theirs."""
    want, have = Layout(ds.partition, ds.sort), layout(con, ds.schema, ds.table)
    if want.partition != have.partition:
        raise LayoutDrift(
            f"{ds.name} is partitioned by {have.partition}, the registry says {want.partition}. "
            f"Restage it with: nbalake stage --rebuild {ds.name}"
        )
    if want.sort != have.sort:
        with transaction(con):
            set_layout(con, ds.qualified, want, have)


def reconcile(con: duckdb.DuckDBPyConnection, ds: Dataset, incoming: dict[str, str]) -> None:
    have = columns(con, ds.qualified)
    for name, typ in incoming.items():
        if name not in have:
            con.execute(f"ALTER TABLE {ds.qualified} ADD COLUMN {quote(name)} {typ}")
            continue
        wider = widen(have[name], typ)
        if wider is None:
            raise SchemaDrift(f"{ds.name}.{name}: table has {have[name]}, incoming unit has {typ}")
        if wider != have[name]:
            con.execute(f"ALTER TABLE {ds.qualified} ALTER COLUMN {quote(name)} TYPE {wider}")


@dataclass(frozen=True, slots=True)
class Load:
    rec: FetchRecord
    supersedes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UnitPlan:
    """drops are units gone upstream. A load drops the versions it supersedes itself."""

    drops: tuple[tuple[str, str], ...]
    loads: tuple[Load, ...]


def plan(want: dict[tuple[str, str], FetchRecord], have: set[tuple[str, str]]) -> UnitPlan:
    stale = sorted(pair for pair in have if pair not in want)
    add = [rec for pair, rec in want.items() if pair not in have]
    replaced = {rec.key for rec in add}
    return UnitPlan(
        drops=tuple(pair for pair in stale if pair[0] not in replaced),
        loads=tuple(Load(rec, tuple(sha for unit, sha in stale if unit == rec.key)) for rec in add),
    )


class Loaded(NamedTuple):
    key: str
    rows: int


@dataclass(slots=True)
class StageReport:
    loaded: dict[str, list[Loaded]] = field(default_factory=dict[str, list["Loaded"]])
    dropped: dict[str, int] = field(default_factory=dict[str, int])
    unchanged: list[str] = field(default_factory=list[str])
    missing: list[str] = field(default_factory=list[str])
    failed: dict[str, dict[str, str]] = field(default_factory=dict[str, dict[str, str]])
    retired: list[str] = field(default_factory=list[str])


ProgressFn = Callable[[Dataset, FetchRecord, int], None]


def staged_pairs(con: duckdb.DuckDBPyConnection, ds: Dataset) -> set[tuple[str, str]]:
    if not table_exists(con, ds.schema, ds.table):
        forget_dataset(con, ds.name)
        return set()
    rows = con.execute(
        "SELECT unit, sha256 FROM lake.meta.staged_units WHERE dataset = ?", [ds.name]
    ).fetchall()
    return {(u, s) for u, s in rows}


def stage(
    root: Root,
    con: duckdb.DuckDBPyConnection,
    datasets: Iterable[Dataset],
    *,
    rebuild: bool = False,
    progress: ProgressFn | None = None,
    registry: Iterable[Dataset] | None = None,
) -> StageReport:
    report = StageReport()
    if registry is not None:
        report.retired = retire(con, registry)
    records = RawStore(root).records()
    for ds in datasets:
        want = {(r.key, r.sha256): r for r in units_in_store(ds, records)}
        if not want:
            report.missing.append(ds.name)
            continue
        if rebuild and table_exists(con, ds.schema, ds.table):
            with transaction(con):
                con.execute(f"DROP TABLE {ds.qualified}")
                forget_dataset(con, ds.name)
        if table_exists(con, ds.schema, ds.table):
            try:
                align_layout(con, ds)
            except LayoutDrift as e:
                report.failed.setdefault(ds.name, {})["layout"] = f"LayoutDrift: {e}"
                continue
            try:
                with transaction(con):
                    backfill_chunks(con, ds)
            except Exception as e:
                report.failed.setdefault(ds.name, {})["chunks"] = f"{type(e).__name__}: {e}"
        units = plan(want, staged_pairs(con, ds))
        if not units.drops and not units.loads:
            report.unchanged.append(ds.name)
            continue
        for unit, sha in units.drops:
            try:
                with transaction(con):
                    drop_unit(con, ds, unit, sha)
            except Exception as e:
                report.failed.setdefault(ds.name, {})[unit] = f"{type(e).__name__}: {e}"
                continue
            report.dropped[ds.name] = report.dropped.get(ds.name, 0) + 1
        for load in units.loads:
            rec = load.rec
            try:
                with transaction(con), open_source(con, root, ds, rec) as src:
                    for sha in load.supersedes:
                        drop_unit(con, ds, rec.key, sha)
                    n = load_unit(con, ds, rec, src)
                    con.execute(
                        "INSERT INTO lake.meta.staged_units VALUES (?, ?, ?, ?, ?, ?)",
                        [ds.name, rec.key, rec.sha256, rec.fetched_at, n, utcnow()],
                    )
                    record_chunks(con, ds, rec.key, rec.sha256)
            except Exception as e:
                report.failed.setdefault(ds.name, {})[rec.key] = f"{type(e).__name__}: {e}"
                continue
            if load.supersedes:
                report.dropped[ds.name] = report.dropped.get(ds.name, 0) + len(load.supersedes)
            report.loaded.setdefault(ds.name, []).append(Loaded(rec.key, n))
            if progress:
                progress(ds, rec, n)
    return report
