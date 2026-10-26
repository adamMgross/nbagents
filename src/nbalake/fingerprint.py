from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, cast

import duckdb

from nbalake.models.model import CURATED, Model

Units = dict[str, tuple[tuple[str, str, str], ...]]
Published = dict[tuple[str, str | None], str]


@dataclass(frozen=True, slots=True)
class Fingerprint:
    model: str
    chunks: dict[str, str]
    column: str | None = None

    def effective(self) -> str:
        """What a dependent sees: the model and every chunk."""
        return digest(self.model, sorted(self.chunks.items())) if self.chunks else self.model


@dataclass(frozen=True, slots=True)
class Skip:
    pass


@dataclass(frozen=True, slots=True)
class Full:
    pass


@dataclass(frozen=True, slots=True)
class Chunks:
    rebuild: tuple[str, ...]
    delete: tuple[str, ...]


Plan = Skip | Full | Chunks


def digest(*parts: Any) -> str:
    text = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Relations:
    tables: tuple[str, ...]
    functions: tuple[str, ...]


def relations(con: duckdb.DuckDBPyConnection, sql: str) -> Relations:
    """Schema-qualified tables and the table functions the SQL reads. Unqualified names are
    CTEs, since a table in the lake cannot bind without its schema."""
    tree = json.loads(con.execute("SELECT json_serialize_sql(?)", [sql]).fetchall()[0][0])
    if tree.get("error"):
        raise ValueError(f"cannot parse SQL: {tree.get('error_message')}")
    tables: set[str] = set()
    functions: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            fields = cast(dict[str, object], node)
            if fields.get("type") == "BASE_TABLE" and fields.get("schema_name"):
                tables.add(f"{fields['schema_name']}.{fields['table_name']}")
            if fields.get("type") == "TABLE_FUNCTION":
                call = cast(dict[str, object], fields["function"])
                functions.add(str(call["function_name"]))
            for v in fields.values():
                walk(v)
        elif isinstance(node, list):
            for v in cast(list[object], node):
                walk(v)

    walk(tree)
    return Relations(tuple(sorted(tables)), tuple(sorted(functions)))


def references(con: duckdb.DuckDBPyConnection, sql: str) -> tuple[str, ...]:
    return relations(con, sql).tables


def staged_units(con: duckdb.DuckDBPyConnection) -> Units:
    rows = con.execute(
        "SELECT dataset, unit, sha256, staged_at::VARCHAR FROM lake.meta.staged_units ORDER BY ALL"
    ).fetchall()
    units: defaultdict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for dataset, unit, sha, at in rows:
        units[dataset].append((unit, sha, at))
    return {k: tuple(v) for k, v in units.items()}


def matches(value: object) -> str:
    """The predicate that selects one chunk, as a literal so DuckLake prunes files by it."""
    if value is None:
        return "IS NULL"
    if isinstance(value, str):
        return "= '" + value.replace("'", "''") + "'"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"= {value}"
    raise TypeError(f"a chunk value must be an integer or a string, not {value!r}")


def chunk_units(
    con: duckdb.DuckDBPyConnection, table: str, column: str, units: Units
) -> dict[str, str]:
    """Each chunk's predicate and a digest of the staged units its rows in table came from."""
    rows = recorded_chunks(con, table, column)
    if rows is None:
        rows = con.execute(f'SELECT DISTINCT "{column}", _unit, _sha256 FROM {table}').fetchall()
    staged_at = {(u, s): at for u, s, at in units.get(table, ())}
    by_chunk: defaultdict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for value, unit, sha in rows:
        by_chunk[matches(value)].append((unit, sha, staged_at.get((unit, sha), "")))
    return {p: digest(sorted(u)) for p, u in sorted(by_chunk.items())}


def recorded_chunks(
    con: duckdb.DuckDBPyConnection, table: str, column: str
) -> list[tuple[object, str, str]] | None:
    """The values stage recorded, or None unless every staged unit with rows has them."""
    rows = con.execute(
        "SELECT value, unit, sha256 FROM lake.meta.unit_chunks "
        "WHERE dataset = ? AND column_name = ?",
        [table, column],
    ).fetchall()
    unrecorded = con.execute(
        "SELECT count(*) FROM (SELECT unit, sha256 FROM lake.meta.staged_units "
        "WHERE dataset = ? AND rows > 0 EXCEPT SELECT unit, sha256 FROM lake.meta.unit_chunks "
        "WHERE dataset = ? AND column_name = ?)",
        [table, table, column],
    ).fetchall()[0][0]
    if not rows or unrecorded:
        return None
    return [(json.loads(v), u, s) for v, u, s in rows]


def _has_column(con: duckdb.DuckDBPyConnection, table: str, column: str) -> bool:
    schema, name = table.split(".", 1)
    found = con.execute(
        "SELECT count(*) FROM duckdb_columns() WHERE database_name = 'lake' "
        "AND schema_name = ? AND table_name = ? AND column_name = ?",
        [schema, name, column],
    ).fetchall()
    return bool(found[0][0])


def fingerprint(
    con: duckdb.DuckDBPyConnection,
    model: Model,
    sql: str,
    seed_digest: str,
    units: Units,
    upstream: dict[str, Fingerprint],
) -> Fingerprint:
    """upstream holds each curated model built earlier in the plan."""
    refs = references(con, sql)
    staged_refs = [r for r in refs if not r.startswith(f"{CURATED}.")]
    curated_refs = {
        r: upstream.get(r.removeprefix(f"{CURATED}.")) for r in refs if r not in staged_refs
    }
    column = model.chunk.column if model.chunk else None
    by_chunk = {r for r in staged_refs if column and _has_column(con, r, column)}
    if model.chunk:
        by_chunk.add(model.chunk.source)
    aligned = {r: u for r, u in curated_refs.items() if u and column and u.column == column}
    whole = digest(
        model.name,
        model.kind.value,
        model.partition,
        model.sort,
        (model.chunk.column, model.chunk.source) if model.chunk else None,
        sql,
        seed_digest,
        {r: digest(units.get(r, ())) for r in staged_refs if r not in by_chunk},
        {
            r: (u.model if r in aligned else u.effective()) if u else ""
            for r, u in curated_refs.items()
        },
    )
    if model.chunk is None:
        return Fingerprint(whole, {})
    staged_chunks = {r: chunk_units(con, r, model.chunk.column, units) for r in sorted(by_chunk)}
    chunks = {
        p: digest(
            whole,
            p,
            {r: d.get(p, "") for r, d in staged_chunks.items()},
            {r: u.chunks.get(p, "") for r, u in aligned.items()},
        )
        for p in staged_chunks[model.chunk.source]
    }
    return Fingerprint(whole, chunks, model.chunk.column)


def plan(name: str, fp: Fingerprint, published: Published, exists: bool) -> Plan:
    if not exists or published.get((name, None)) != fp.model:
        return Full()
    had = {c for (m, c) in published if m == name and c is not None}
    rebuild = tuple(p for p, f in fp.chunks.items() if published.get((name, p)) != f)
    delete = tuple(sorted(had - fp.chunks.keys()))
    if not rebuild and not delete:
        return Skip()
    return Chunks(rebuild, delete)
