from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import duckdb

from nbalake import fingerprint as fpr
from nbalake.lake import CURATE_COMMIT, Layout, quote, set_layout, transaction, utcnow
from nbalake.models import ALL, Kind, Model
from nbalake.models.model import CURATED, Chunk
from nbalake.profile import write_catalog

SQL = Path(str(resources.files("nbalake") / "sql"))


@dataclass(frozen=True, slots=True)
class Step:
    model: Model
    sql: str
    seed_digest: str = ""


@dataclass(frozen=True, slots=True)
class Gate:
    name: str
    sql: str


@dataclass(frozen=True, slots=True)
class GateResult:
    gate: str
    violations: int
    sample: list[dict[str, object]]

    @property
    def ok(self) -> bool:
        return self.violations == 0


class GateFailure(Exception):
    def __init__(self, results: list[GateResult]) -> None:
        self.results = results
        failed = [r for r in results if not r.ok]
        super().__init__(
            "quality gates failed: "
            + ", ".join(f"{r.gate} ({r.violations} violations)" for r in failed)
        )


def seed_sql(path: Path) -> str:
    quoted = str(path).replace("'", "''")
    return f"SELECT * FROM read_csv('{quoted}', header=true, nullstr=['', 'NA'])"


def step(model: Model) -> Step:
    match model.kind:
        case Kind.SEED:
            path = SQL / "seed" / f"{model.name}.csv"
            return Step(model, seed_sql(path), hashlib.sha256(path.read_bytes()).hexdigest())
        case Kind.TABLE | Kind.VIEW:
            return Step(model, (SQL / "models" / f"{model.name}.sql").read_text(encoding="utf-8"))


def shipped_steps(models: Sequence[Model] = ALL) -> tuple[Step, ...]:
    return tuple(step(m) for m in models)


def shipped_gates(prefix: str = "") -> tuple[Gate, ...]:
    return tuple(
        Gate(p.stem, p.read_text(encoding="utf-8"))
        for p in sorted((SQL / "gates").glob(f"{prefix}*.sql"))
    )


def _count(con: duckdb.DuckDBPyConnection, relation: str) -> int:
    return int(con.execute(f"SELECT count(*) FROM {relation}").fetchall()[0][0])


def build(
    con: duckdb.DuckDBPyConnection, s: Step, chunks: Sequence[str] | None = None
) -> int | None:
    """chunks are the predicates of a chunked model, read from its source when None."""
    model, target = s.model, s.model.qualified
    _drop_other_kind(con, model)
    match model.kind:
        case Kind.VIEW:
            con.execute(f"CREATE OR REPLACE VIEW {target} AS {s.sql}").fetchall()
            return None
        case Kind.TABLE | Kind.SEED:
            con.execute(f"CREATE OR REPLACE TABLE {target} AS SELECT * FROM ({s.sql}) LIMIT 0")
            set_layout(con, target, Layout(model.partition, model.sort))
            if model.chunk is None:
                return _insert(con, s, None)
            if chunks is None:
                chunks = chunk_matches(con, model.chunk)
            return sum(_insert(con, s, c) for c in chunks)


def rebuild_chunks(
    con: duckdb.DuckDBPyConnection, s: Step, rebuild: Sequence[str], delete: Sequence[str]
) -> int:
    assert s.model.chunk is not None
    column = quote(s.model.chunk.column)
    for c in (*delete, *rebuild):
        con.execute(f"DELETE FROM {s.model.qualified} WHERE {column} {c}").fetchall()
    return sum(_insert(con, s, c) for c in rebuild)


def _insert(con: duckdb.DuckDBPyConnection, s: Step, chunk: str | None) -> int:
    model = s.model
    where = f" WHERE {quote(model.chunk.column)} {chunk}" if model.chunk and chunk else ""
    order = f" ORDER BY {', '.join(quote(c) for c in model.sort)}" if model.sort else ""
    inserted = con.execute(
        f"INSERT INTO {model.qualified} SELECT * FROM ({s.sql}){where}{order}"
    ).fetchall()
    return int(inserted[0][0])


def chunk_matches(con: duckdb.DuckDBPyConnection, chunk: Chunk) -> list[str]:
    rows = con.execute(
        f"SELECT DISTINCT {quote(chunk.column)} FROM {chunk.source} ORDER BY 1 NULLS LAST"
    ).fetchall()
    return [fpr.matches(v) for (v,) in rows]


def _exists(con: duckdb.DuckDBPyConnection, name: str, view: bool) -> bool:
    catalog, column = ("duckdb_views()", "view_name") if view else ("duckdb_tables()", "table_name")
    found = con.execute(
        f"SELECT count(*) FROM {catalog} WHERE database_name = 'lake' "
        f"AND schema_name = ? AND {column} = ?",
        [CURATED, name],
    ).fetchall()
    return bool(found[0][0])


def _drop_other_kind(con: duckdb.DuckDBPyConnection, model: Model) -> None:
    view = model.kind is Kind.VIEW
    if _exists(con, model.name, view=not view):
        con.execute(f"DROP {'TABLE' if view else 'VIEW'} {model.qualified}").fetchall()


def check(con: duckdb.DuckDBPyConnection, gate: Gate, sample_rows: int = 5) -> GateResult:
    cur = con.execute(f"SELECT * FROM ({gate.sql}) LIMIT {sample_rows}")
    cols = [d[0] for d in cur.description or ()]
    sample = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    return GateResult(gate.name, _count(con, f"({gate.sql})"), sample)


@dataclass(slots=True)
class CurateReport:
    """rows holds what this run built, None for a view. chunks counts rebuilt chunks."""

    rows: dict[str, int | None]
    gates: list[GateResult]
    committed: bool
    skipped: list[str] = field(default_factory=list[str])
    chunks: dict[str, int] = field(default_factory=dict[str, int])
    retired: list[str] = field(default_factory=list[str])


def retire(con: duckdb.DuckDBPyConnection, keep: set[str]) -> list[str]:
    """Drops every curated table and view whose name is not in keep, with its fingerprints."""
    found = con.execute(
        "SELECT table_name, 'TABLE' FROM duckdb_tables() WHERE database_name = 'lake' "
        "AND schema_name = ? UNION ALL SELECT view_name, 'VIEW' FROM duckdb_views() "
        "WHERE database_name = 'lake' AND schema_name = ? ORDER BY 1",
        [CURATED, CURATED],
    ).fetchall()
    retired = [(name, kind) for name, kind in found if name not in keep]
    for name, kind in retired:
        con.execute(f'DROP {kind} lake."{CURATED}".{quote(name)}').fetchall()
        con.execute("DELETE FROM lake.meta.fingerprints WHERE model = ?", [name]).fetchall()
    return [name for name, _ in retired]


def curate(
    con: duckdb.DuckDBPyConnection,
    *,
    run_id: str,
    steps: Sequence[Step] | None = None,
    gates: Sequence[Gate] | None = None,
    enforce_gates: bool = True,
    rebuild: bool = False,
    registry: Sequence[Model] | None = None,
) -> CurateReport:
    """Builds only models whose fingerprint differs from the published one, unless rebuild.

    With a registry, curated tables and views no registered model or step produces are dropped.
    """
    steps = shipped_steps() if steps is None else steps
    gates = shipped_gates() if gates is None else gates
    con.execute(f'CREATE SCHEMA IF NOT EXISTS lake."{CURATED}"')
    report = CurateReport(rows={}, gates=[], committed=True)
    units = fpr.staged_units(con)
    published = {} if rebuild else _published(con)
    upstream: dict[str, fpr.Fingerprint] = {}
    prints: dict[str, fpr.Fingerprint] = {}
    try:
        with transaction(con):
            for s in steps:
                name = s.model.name
                fp = fpr.fingerprint(con, s.model, s.sql, s.seed_digest, units, upstream)
                prints[name] = upstream[name] = fp
                exists = _exists(con, name, view=s.model.kind is Kind.VIEW)
                match fpr.plan(name, fp, published, exists):
                    case fpr.Skip():
                        report.skipped.append(name)
                    case fpr.Full():
                        report.rows[name] = build(con, s, tuple(fp.chunks) or None)
                        if s.model.chunk:
                            report.chunks[name] = len(fp.chunks)
                    case fpr.Chunks(rebuild=again, delete=gone):
                        report.rows[name] = rebuild_chunks(con, s, again, gone)
                        report.chunks[name] = len(again)
            if registry is not None:
                keep = {m.name for m in registry} | {s.model.name for s in steps}
                report.retired = retire(con, keep)
            report.gates = [check(con, g) for g in gates]
            if enforce_gates and any(not r.ok for r in report.gates):
                raise GateFailure(report.gates)
            write_catalog(
                con,
                {s.model.name: s.sql for s in steps},
                list(
                    {**{m.name: m for m in ALL}, **{s.model.name: s.model for s in steps}}.values()
                ),
                unchanged=set(report.skipped),
                gate_sql={g.name: g.sql for g in gates},
            )
            _record_fingerprints(con, run_id, prints)
            con.execute(
                "CALL ducklake_set_commit_message('lake', 'nbalake', ?, extra_info => ?)",
                [CURATE_COMMIT, run_id],
            ).fetchall()
    finally:
        _record_gates(con, run_id, report.gates)
    return report


def _published(con: duckdb.DuckDBPyConnection) -> fpr.Published:
    rows = con.execute("SELECT model, chunk, fingerprint FROM lake.meta.fingerprints").fetchall()
    return {(m, c): f for m, c, f in rows}


def _record_fingerprints(
    con: duckdb.DuckDBPyConnection, run_id: str, prints: dict[str, fpr.Fingerprint]
) -> None:
    if not prints:
        return
    names = list(prints)
    con.execute(
        f"DELETE FROM lake.meta.fingerprints WHERE model IN ({', '.join('?' * len(names))})",
        names,
    ).fetchall()
    rows = [
        row
        for name, fp in prints.items()
        for row in [(name, None, fp.model), *((name, c, f) for c, f in fp.chunks.items())]
    ]
    values = ", ".join(["(?, ?, ?, ?)"] * len(rows))
    params = [v for row in rows for v in (*row, run_id)]
    con.execute(f"INSERT INTO lake.meta.fingerprints VALUES {values}", params).fetchall()


def _record_gates(con: duckdb.DuckDBPyConnection, run_id: str, results: list[GateResult]) -> None:
    if not results:
        return
    now = utcnow()
    values = ", ".join(["(?, ?, ?, ?, ?)"] * len(results))
    params = [
        v
        for r in results
        for v in (run_id, r.gate, r.violations, json.dumps(r.sample, default=str), now)
    ]
    con.execute(f"INSERT INTO lake.meta.gate_results VALUES {values}", params)
