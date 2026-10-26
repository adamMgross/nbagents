from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

import duckdb
import pyarrow as pa

from nbalake import datasets
from nbalake.fingerprint import references
from nbalake.lake import META_SCHEMA, utcnow
from nbalake.model import License
from nbalake.models import ALL, Model
from nbalake.models.model import CURATED

TOP_VALUES_UNDER = 20
EXAMPLE_WIDTH = 60
STAGED_REF = re.compile(rf"\b((?:{'|'.join(datasets.SCHEMAS)})\.\w+)")

COVERAGE = pa.list_(pa.struct([("season", pa.int32()), ("rows", pa.int64())]))
CATALOG = pa.schema(
    [
        ("schema", pa.string()),
        ("name", pa.string()),
        ("kind", pa.string()),
        ("rows", pa.int64()),
        ("rows_from", pa.string()),
        ("grain", pa.list_(pa.string())),
        ("partition", pa.string()),
        ("sort", pa.list_(pa.string())),
        ("season_min", pa.int32()),
        ("season_max", pa.int32()),
        ("coverage", COVERAGE),
        ("description", pa.string()),
        ("profiled_at", pa.timestamp("us")),
        ("sources", pa.list_(pa.string())),
        ("gates", pa.list_(pa.string())),
        ("license", pa.string()),
    ]
)
TYPED_COVERAGE = pa.schema(
    [
        ("schema", pa.string()),
        ("name", pa.string()),
        ("season_type", pa.string()),
        ("season", pa.int32()),
        ("rows", pa.int64()),
    ]
)
COLUMNS = pa.schema(
    [
        ("schema", pa.string()),
        ("name", pa.string()),
        ("column_name", pa.string()),
        ("ordinal", pa.int32()),
        ("type", pa.string()),
        ("null_percent", pa.float64()),
        ("min", pa.string()),
        ("max", pa.string()),
        ("distinct", pa.int64()),
        ("top", pa.list_(pa.struct([("value", pa.string()), ("rows", pa.int64())]))),
        ("example", pa.string()),
    ]
)


@dataclass(frozen=True, slots=True)
class TypedSeason:
    season_type: str | None
    season: int
    rows: int


@dataclass(frozen=True, slots=True)
class Relation:
    schema: str
    name: str
    is_view: bool
    estimated_rows: int | None

    @property
    def sql(self) -> str:
        return f'lake."{self.schema}"."{self.name}"'


def _relations(con: duckdb.DuckDBPyConnection) -> list[Relation]:
    rows = con.execute(
        f"""
        SELECT schema_name, table_name, false, estimated_size FROM duckdb_tables()
        WHERE database_name = 'lake' AND schema_name <> '{META_SCHEMA}'
        UNION ALL
        SELECT schema_name, view_name, true, NULL FROM duckdb_views()
        WHERE database_name = 'lake' AND schema_name <> '{META_SCHEMA}' AND NOT internal
        ORDER BY 1, 2
        """
    ).fetchall()
    return [Relation(s, n, v, r) for s, n, v, r in rows]


def _columns(con: duckdb.DuckDBPyConnection, rel: Relation) -> list[tuple[str, str]]:
    return [(c, t) for c, t, *_ in con.execute(f"DESCRIBE {rel.sql}").fetchall()]


class TypeSource(Enum):
    GAMES = "games"
    COLUMN = "column"
    NONE = "none"


def type_source(schema: str, columns: set[str], games_exist: bool) -> TypeSource:
    """A curated game's season type is the one nba.games gives it, in its vocabulary."""
    if schema == CURATED and "game_id" in columns and games_exist:
        return TypeSource.GAMES
    return TypeSource.COLUMN if "season_type" in columns else TypeSource.NONE


def _coverage(
    con: duckdb.DuckDBPyConnection, rel: Relation, source: TypeSource
) -> list[TypedSeason]:
    match source:
        case TypeSource.GAMES:
            sql = (
                "SELECT g.season_type, c.s, sum(c.n)::BIGINT FROM ("
                f"SELECT game_id, TRY_CAST(season AS INTEGER) AS s, count(*) AS n FROM {rel.sql} "
                f'GROUP BY 1, 2) c LEFT JOIN lake."{CURATED}".games g USING (game_id) '
                "WHERE c.s IS NOT NULL GROUP BY 1, 2"
            )
        case TypeSource.COLUMN | TypeSource.NONE:
            season_type = "season_type" if source is TypeSource.COLUMN else "NULL"
            sql = (
                f"SELECT {season_type}::VARCHAR, TRY_CAST(season AS INTEGER) AS s, count(*) "
                f"FROM {rel.sql} WHERE s IS NOT NULL GROUP BY 1, 2"
            )
    rows = con.execute(f"{sql} ORDER BY 1 NULLS FIRST, 2").fetchall()
    return [TypedSeason(t, s, n) for t, s, n in rows]


def _by_season(typed: list[TypedSeason]) -> list[dict[str, int]]:
    totals: dict[int, int] = {}
    for c in typed:
        totals[c.season] = totals.get(c.season, 0) + c.rows
    return [{"season": s, "rows": n} for s, n in sorted(totals.items())]


def _example(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= EXAMPLE_WIDTH else text[: EXAMPLE_WIDTH - 3] + "..."


def _column_stats(con: duckdb.DuckDBPyConnection, rel: Relation) -> list[dict[str, object]]:
    first = con.execute(f"SELECT * FROM {rel.sql} LIMIT 1").fetchall()
    example = first[0] if first else None
    out: list[dict[str, object]] = []
    summary = con.execute(f"SUMMARIZE {rel.sql}").fetchall()
    for i, (name, typ, lo, hi, distinct, *_rest, null_pct) in enumerate(summary):
        top = None
        if distinct is not None and 0 < distinct < TOP_VALUES_UNDER:
            values = con.execute(
                f'SELECT "{name}", count(*) FROM {rel.sql} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 5'
            ).fetchall()
            top = [{"value": "NULL" if v is None else str(v), "rows": n} for v, n in values]
        out.append(
            {
                "column_name": name,
                "ordinal": i,
                "type": typ,
                "null_percent": None if null_pct is None else float(null_pct),
                "min": _example(lo),
                "max": _example(hi),
                "distinct": distinct,
                "top": top,
                "example": None if example is None else _example(example[i]),
            }
        )
    return out


def _bare_columns(con: duckdb.DuckDBPyConnection, rel: Relation) -> list[dict[str, object]]:
    return [
        {
            "column_name": c,
            "ordinal": i,
            "type": t,
            "null_percent": None,
            "min": None,
            "max": None,
            "distinct": None,
            "top": None,
            "example": None,
        }
        for i, (c, t) in enumerate(_columns(con, rel))
    ]


def view_sources(view_sql: dict[str, str]) -> dict[str, str]:
    """The staged table each curated view reads, for views that read exactly one."""
    out: dict[str, str] = {}
    for name, sql in view_sql.items():
        refs = set(STAGED_REF.findall(sql))
        if len(refs) == 1:
            out[name] = refs.pop()
    return out


@dataclass(frozen=True, slots=True)
class Profiled:
    rows: int
    columns: list[dict[str, object]]


def lineage(
    con: duckdb.DuckDBPyConnection, model_sql: dict[str, str], gate_sql: dict[str, str]
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """The relations each curated model reads, and the gates that read each curated model."""
    reads = {
        n: [r for r in references(con, sql) if r != f"{CURATED}.{n}"]
        for n, sql in model_sql.items()
    }
    gated: dict[str, list[str]] = {}
    for gate, sql in sorted(gate_sql.items()):
        for ref in references(con, sql):
            schema, _, name = ref.partition(".")
            if schema == CURATED:
                gated.setdefault(name, []).append(gate)
    return reads, gated


def personal_relations(reads: dict[str, list[str]], personal: set[str]) -> set[str]:
    """The personal relations plus every curated model that reads one, directly or through
    another model. reads maps a model name to the relations it reads."""
    found = set(personal)
    grew = True
    while grew:
        grew = False
        for name, refs in reads.items():
            qualified = f"{CURATED}.{name}"
            if qualified not in found and any(r in found for r in refs):
                found.add(qualified)
                grew = True
    return found


def profile(
    con: duckdb.DuckDBPyConnection,
    model_sql: dict[str, str],
    models: Sequence[Model] = ALL,
    reuse: dict[str, Profiled] | None = None,
    gate_sql: dict[str, str] | None = None,
    registry: Sequence[datasets.Dataset] = datasets.ALL,
) -> tuple[pa.Table, pa.Table, pa.Table]:
    """model_sql holds every built model's SQL. reuse holds curated tables whose rows and
    column stats are still current."""
    reuse = reuse or {}
    by_model = {m.name: m for m in models}
    by_dataset = {d.name: d for d in registry}
    sources = view_sources(model_sql)
    reads, gated = lineage(con, model_sql, gate_sql or {})
    personal = personal_relations(
        reads, {d.name for d in registry if d.license is License.PERSONAL}
    )
    relations = _relations(con)
    coverage: dict[str, list[TypedSeason]] = {}
    tables: list[dict[str, object]] = []
    columns: list[dict[str, object]] = []
    typed: list[dict[str, object]] = []
    now = utcnow()
    games_exist = any(r.schema == CURATED and r.name == "games" for r in relations)
    for rel in relations:
        names = {c for c, _ in _columns(con, rel)}
        source = type_source(rel.schema, names, games_exist)
        if "season" in names and (not rel.is_view or source is TypeSource.GAMES):
            coverage[f"{rel.schema}.{rel.name}"] = _coverage(con, rel, source)
    for rel in relations:
        qualified = f"{rel.schema}.{rel.name}"
        model = by_model.get(rel.name) if rel.schema == CURATED else None
        dataset = by_dataset.get(qualified)
        rows_from = sources.get(rel.name) if rel.is_view else None
        measured = coverage.get(qualified) or coverage.get(rows_from or "", [])
        for c in measured:
            typed.append(
                {
                    "schema": rel.schema,
                    "name": rel.name,
                    "season_type": c.season_type,
                    "season": c.season,
                    "rows": c.rows,
                }
            )
        cov = _by_season(measured)
        if rel.is_view:
            rows = sum(c["rows"] for c in cov) if rows_from else None
            cols = _bare_columns(con, rel)
        elif model is not None and rel.name in reuse:
            rows, cols = reuse[rel.name].rows, reuse[rel.name].columns
        elif model is not None:
            rows = int(con.execute(f"SELECT count(*) FROM {rel.sql}").fetchall()[0][0])
            cols = _column_stats(con, rel)
        else:
            rows = sum(c["rows"] for c in cov) if cov else rel.estimated_rows
            cols = _bare_columns(con, rel)
        kind = model.kind.value if model is not None else ("view" if rel.is_view else "staged")
        source = model or dataset
        tables.append(
            {
                "schema": rel.schema,
                "name": rel.name,
                "kind": kind,
                "rows": rows,
                "rows_from": rows_from,
                "grain": list(model.grain) if model else [],
                "partition": source.partition if source else None,
                "sort": list(source.sort) if source else [],
                "season_min": cov[0]["season"] if cov else None,
                "season_max": cov[-1]["season"] if cov else None,
                "coverage": cov,
                "description": source.description if source else "",
                "profiled_at": now,
                "sources": reads.get(rel.name, []) if model else [],
                "gates": gated.get(rel.name, []) if model else [],
                "license": License.PERSONAL.value if qualified in personal else License.OPEN.value,
            }
        )
        columns += [{"schema": rel.schema, "name": rel.name, **c} for c in cols]
    return (
        pa.Table.from_pylist(tables, schema=CATALOG),
        pa.Table.from_pylist(columns, schema=COLUMNS),
        pa.Table.from_pylist(typed, schema=TYPED_COVERAGE),
    )


def published(con: duckdb.DuckDBPyConnection, names: set[str]) -> dict[str, Profiled]:
    """The published profile of each named curated table, where one exists."""
    exists = con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE database_name = 'lake' "
        "AND schema_name = ? AND table_name IN ('catalog', 'catalog_columns')",
        [META_SCHEMA],
    ).fetchall()[0][0]
    if exists < 2 or not names:
        return {}
    wanted = list(names)
    marks = ", ".join("?" * len(wanted))
    counts = dict(
        con.execute(
            f"SELECT name, rows FROM lake.{META_SCHEMA}.catalog "
            f"WHERE schema = ? AND name IN ({marks}) AND rows IS NOT NULL",
            [CURATED, *wanted],
        ).fetchall()
    )
    stats = con.execute(
        f"SELECT * EXCLUDE (schema) FROM lake.{META_SCHEMA}.catalog_columns "
        f"WHERE schema = ? AND name IN ({marks}) ORDER BY name, ordinal",
        [CURATED, *wanted],
    ).fetchall()
    keys = [d[0] for d in con.description or ()]
    columns: dict[str, list[dict[str, object]]] = {}
    for row in stats:
        record = dict(zip(keys, row, strict=True))
        columns.setdefault(str(record.pop("name")), []).append(record)
    return {n: Profiled(int(counts[n]), columns[n]) for n in counts if n in columns}


def write_catalog(
    con: duckdb.DuckDBPyConnection,
    model_sql: dict[str, str],
    models: Sequence[Model] = ALL,
    unchanged: set[str] | None = None,
    gate_sql: dict[str, str] | None = None,
    registry: Sequence[datasets.Dataset] = datasets.ALL,
) -> int:
    """unchanged names curated tables this run did not rebuild, whose profiles are kept."""
    reuse = published(con, unchanged or set())
    catalog, columns, coverage = profile(con, model_sql, models, reuse, gate_sql, registry)
    for name, table in (
        ("catalog", catalog),
        ("catalog_columns", columns),
        ("catalog_coverage", coverage),
    ):
        con.register("_profile", table)
        con.execute(f"CREATE OR REPLACE TABLE lake.{META_SCHEMA}.{name} AS FROM _profile")
        con.unregister("_profile")
    return catalog.num_rows
