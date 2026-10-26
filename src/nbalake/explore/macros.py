from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from graphlib import TopologicalSorter
from importlib import resources
from importlib.resources.abc import Traversable

import duckdb

SIGNATURE = re.compile(r"CREATE OR REPLACE TEMP MACRO (\w+)\((.*?)\) AS", re.DOTALL)
STRINGS_AND_COMMENTS = re.compile(r"'(?:[^']|'')*'|--[^\n]*|/\*.*?\*/", re.DOTALL)


@dataclass(frozen=True, slots=True)
class Macro:
    name: str
    signature: str
    description: str
    example: str
    sql: str
    body: str
    metric: str | None = None


def _parse(sql: str, metric: str | None = None) -> Macro:
    header = [ln.removeprefix("-- ") for ln in sql.splitlines() if ln.startswith("-- ")]
    description = next(h for h in header if not h.startswith("example: "))
    example = next(h for h in header if h.startswith("example: ")).removeprefix("example: ")
    m = SIGNATURE.search(sql)
    if m is None:
        raise ValueError(f"macro file without a CREATE OR REPLACE TEMP MACRO: {sql[:80]!r}")
    body = sql[m.end() :].strip().removeprefix("TABLE").strip()
    return Macro(m[1], f"{m[1]}({m[2]})", description, example, sql, body, metric)


def shipped() -> tuple[Macro, ...]:
    """Every macro, the metrics' included, ordered so a macro loads after the macros it calls."""
    package = resources.files("nbalake")
    found = [_parse(sql) for sql in _sql_in(package / "sql" / "macros")]
    for folder in metric_folders():
        found += [_parse(sql, folder.name) for sql in _sql_in(folder)]
    return in_load_order(found)


def metric_folders() -> list[Traversable]:
    folder = resources.files("nbalake") / "metrics"
    return sorted((f for f in folder.iterdir() if f.is_dir() and f.name[0].isalpha()), key=str)


def _sql_in(folder: Traversable) -> list[str]:
    return [f.read_text(encoding="utf-8") for f in folder.iterdir() if f.name.endswith(".sql")]


def in_load_order(found: Iterable[Macro]) -> tuple[Macro, ...]:
    """Callees before callers, and by name among macros that are ready together."""
    by_name = {m.name: m for m in found}
    calls = {n: set(_calls(m.body, by_name)) - {n} for n, m in by_name.items()}
    order = TopologicalSorter(calls)
    order.prepare()
    loaded: list[Macro] = []
    while order.is_active():
        ready = sorted(order.get_ready())
        loaded += [by_name[n] for n in ready]
        order.done(*ready)
    return tuple(loaded)


def called_by(queries: Iterable[str], available: Iterable[Macro]) -> tuple[Macro, ...]:
    """The macros the queries call, directly or through other macros, callers before callees."""
    by_name = {m.name: m for m in available}
    queue = deque(n for q in queries for n in _calls(q, by_name))
    seen: dict[str, Macro] = {}
    while queue:
        name = queue.popleft()
        if name not in seen:
            seen[name] = by_name[name]
            queue.extend(_calls(by_name[name].body, by_name))
    return tuple(seen.values())


def _calls(sql: str, names: Iterable[str]) -> list[str]:
    code = STRINGS_AND_COMMENTS.sub(" ", sql)
    found = ((m.start(), n) for n in names if (m := re.search(rf"\b{n}\s*\(", code)))
    return [n for _, n in sorted(found)]


def load(con: duckdb.DuckDBPyConnection) -> None:
    for m in shipped():
        con.execute(m.sql)


@dataclass(frozen=True, slots=True)
class ScratchMacro:
    signature: str
    kind: str
    definition: str


def scratch_macros(con: duckdb.DuckDBPyConnection, database: str) -> tuple[ScratchMacro, ...]:
    rows = con.execute(
        "SELECT function_name, parameters, function_type, macro_definition FROM duckdb_functions() "
        "WHERE database_name = ? AND function_type IN ('macro', 'table_macro') ORDER BY ALL",
        [database],
    ).fetchall()
    return tuple(
        ScratchMacro(f"{n}({', '.join(p)})", "table" if t == "table_macro" else "scalar", d)
        for n, p, t, d in rows
    )
