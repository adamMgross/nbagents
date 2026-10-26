from __future__ import annotations

import json
import re
import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import duckdb

from nbalake.explore.session import PROVENANCE, SCRATCH
from nbalake.lake import utcnow

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True, slots=True)
class QueryResult:
    columns: tuple[str, ...]
    types: tuple[str, ...]
    rows: list[tuple[object, ...]]
    truncated: bool


@dataclass(frozen=True, slots=True)
class Saved:
    name: str
    rows: int
    columns: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Scan:
    table: str
    files: int | None
    rows: int


@dataclass(frozen=True, slots=True)
class Explained:
    scans: tuple[Scan, ...]
    bytes_read: int
    seconds: float
    plan: str

    @property
    def files_read(self) -> int:
        return sum(s.files or 0 for s in self.scans)

    def rows_by_table(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for s in self.scans:
            totals[s.table] = totals.get(s.table, 0) + s.rows
        return totals


PLAN_DETAILS = ("Table", "Join Type", "Conditions", "Filters", "Groups", "Aggregates")
HIDDEN_OPERATORS = frozenset({"RESULT_COLLECTOR", "EXPLAIN_ANALYZE"})


class QueryTimeout(Exception):
    def __init__(self, seconds: float) -> None:
        super().__init__(
            f"query stopped after the {seconds:g}s timeout. Narrow it, or raise --timeout."
        )


@contextmanager
def deadline(con: duckdb.DuckDBPyConnection, seconds: float) -> Generator[None]:
    timer = threading.Timer(seconds, con.interrupt)
    timer.start()
    try:
        yield
    except duckdb.InterruptException as e:
        raise QueryTimeout(seconds) from e
    finally:
        timer.cancel()


def run(
    con: duckdb.DuckDBPyConnection, sql: str, *, limit: int, timeout: float
) -> QueryResult | None:
    """Fetches at most limit + 1 rows from a streamed result. None for a statement."""
    with deadline(con, timeout):
        con.execute(sql)
        description = con.description or ()
        rows = con.fetchmany(limit + 1) if description else []
    columns = tuple(d[0] for d in description)
    if not columns or (columns == ("Success",) and not rows):
        return None
    return QueryResult(
        columns=columns,
        types=tuple(str(d[1]) for d in description),
        rows=rows[:limit],
        truncated=len(rows) > limit,
    )


def explain(con: duckdb.DuckDBPyConnection, sql: str, *, timeout: float) -> Explained:
    """Runs the statement under EXPLAIN ANALYZE and discards its rows."""
    with deadline(con, timeout):
        rows = con.execute(f"EXPLAIN (ANALYZE, FORMAT JSON) {sql.strip().rstrip(';')}").fetchall()
    return explained(json.loads(rows[0][1]))


def explained(profile: dict[str, Any]) -> Explained:
    scans: list[Scan] = []
    lines: list[str] = []
    stack: list[tuple[dict[str, Any], int]] = [(n, 0) for n in reversed(profile["operator"])]
    while stack:
        node, depth = stack.pop()
        info: dict[str, Any] = node["extra_info"]
        children: list[dict[str, Any]] = node.get("children", [])
        if node["type"] in HIDDEN_OPERATORS:
            stack += [(c, depth) for c in reversed(children)]
            continue
        rows = int(node["intermediate_rows"])
        files = info.get("Total Files Read")
        if "Table" in info:
            scans.append(Scan(str(info["Table"]), None if files is None else int(files), rows))
        details = [f"{k.lower()}: {_flat(info[k])}" for k in PLAN_DETAILS if k in info]
        if files is not None:
            details.append(f"files read: {files}")
        details.append(f"rows: {rows:,}")
        lines.append("  " * depth + "  ".join([node["type"], *details]))
        stack += [(c, depth + 1) for c in reversed(children)]
    return Explained(
        scans=tuple(scans),
        bytes_read=int(profile["io"]["total_bytes_read"]),
        seconds=float(profile["query"]["total_time"]),
        plan="\n".join(lines),
    )


def _flat(value: str | list[str]) -> str:
    return value if isinstance(value, str) else ", ".join(value)


def save(con: duckdb.DuckDBPyConnection, sql: str, name: str, *, timeout: float) -> Saved:
    """Replaces scratch.<name> with the result and records the SQL in scratch.__provenance."""
    if not IDENTIFIER.fullmatch(name):
        raise ValueError(f"--out takes a plain table name like top_scorers, not {name!r}")
    target = f'{SCRATCH}."{name}"'
    body = sql.strip().rstrip(";")
    con.execute("BEGIN")
    try:
        with deadline(con, timeout):
            con.execute(f"CREATE OR REPLACE TABLE {target} AS {body}").fetchall()
        rows = int(con.execute(f"SELECT count(*) FROM {target}").fetchall()[0][0])
        con.execute(
            f"CREATE TABLE IF NOT EXISTS {SCRATCH}.{PROVENANCE} "
            "(name VARCHAR PRIMARY KEY, sql VARCHAR, rows BIGINT, created_at TIMESTAMP)"
        )
        con.execute(
            f"INSERT OR REPLACE INTO {SCRATCH}.{PROVENANCE} VALUES (?, ?, ?, ?)",
            [name, body, rows, utcnow()],
        )
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    cols = tuple((c, t) for c, t, *_ in con.execute(f"DESCRIBE {target}").fetchall())
    return Saved(f"{SCRATCH}.{name}", rows, cols)


def truncation_notice(limit: int) -> str:
    return (
        f"showing {limit} rows, more exist. Narrow the query, raise --limit, "
        "or add --out <name> to keep every row in scratch.<name>."
    )
