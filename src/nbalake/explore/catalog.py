from __future__ import annotations

import csv
import difflib
import fnmatch
import io
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from importlib import resources

import duckdb

from nbalake import datasets, fingerprint
from nbalake.curate import shipped_steps
from nbalake.explore import macros, metrics
from nbalake.explore.session import PROVENANCE, SCRATCH
from nbalake.lake import META_SCHEMA, table_exists
from nbalake.model import DropFolder, Fetch, GitDir, GitTree, Kaggle, ReleaseAssets
from nbalake.models.model import CURATED, Kind

JOINS = {
    "game_id": "nba.games",
    "player_id": "nba.players",
    "next_series_id": "nba.playoff_series",
    **{
        c: "nba.teams"
        for c in (
            "team_id",
            "opponent_team_id",
            "home_team_id",
            "away_team_id",
            "winner_team_id",
            "home_court_team_id",
            "other_team_id",
            "offense_team_id",
            "defense_team_id",
        )
    },
}


class TableKind(Enum):
    TABLE = "table"
    VIEW = "view"
    SEED = "seed"
    STAGED = "staged"
    SCRATCH = "scratch"


@dataclass(frozen=True, slots=True)
class Season:
    season: int
    rows: int


@dataclass(frozen=True, slots=True)
class TableInfo:
    schema: str
    name: str
    kind: TableKind
    rows: int | None
    description: str
    rows_from: str | None = None
    grain: tuple[str, ...] = ()
    partition: str | None = None
    sort: tuple[str, ...] = ()
    coverage: tuple[Season, ...] = ()
    license: str = "open"

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}"

    @property
    def seasons(self) -> str:
        if not self.coverage:
            return ""
        lo, hi = self.coverage[0].season, self.coverage[-1].season
        return str(lo) if lo == hi else f"{lo}-{hi}"


@dataclass(frozen=True, slots=True)
class Value:
    value: str
    rows: int


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    name: str
    type: str
    null_percent: float | None = None
    min: str | None = None
    max: str | None = None
    distinct: int | None = None
    top: tuple[Value, ...] = ()
    example: str | None = None


@dataclass(frozen=True, slots=True)
class GateStatus:
    name: str
    violations: int | None


@dataclass(frozen=True, slots=True)
class Lineage:
    sources: tuple[str, ...] = ()
    gates: tuple[GateStatus, ...] = ()
    upstream: str | None = None
    units: int | None = None
    sql: str | None = None


@dataclass(frozen=True, slots=True)
class TypeCoverage:
    season_type: str
    seasons: tuple[Season, ...]


@dataclass(frozen=True, slots=True)
class TableDoc:
    table: TableInfo
    columns: tuple[ColumnInfo, ...]
    caveats: tuple[Caveat, ...] = ()
    lineage: Lineage = Lineage()
    by_type: tuple[TypeCoverage, ...] = ()

    @property
    def joins(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (c.name, JOINS[c.name])
            for c in self.columns
            if c.name in JOINS
            and not (JOINS[c.name] == self.table.qualified and c.name in self.table.grain)
        )


@dataclass(frozen=True, slots=True)
class Currency:
    through: date | None
    refreshed_at: datetime | None
    refresh_ok: bool | None
    detail: str
    staged_since_curate: bool


def currency(con: duckdb.DuckDBPyConnection) -> Currency:
    """What the lake is current through and how its last refresh went, from meta tables only."""
    through = None
    if table_exists(con, META_SCHEMA, "catalog_columns"):
        rows = con.execute(
            f"SELECT max FROM lake.{META_SCHEMA}.catalog_columns "
            "WHERE schema = ? AND name = 'games' AND column_name = 'game_date'",
            [CURATED],
        ).fetchall()
        through = date.fromisoformat(rows[0][0]) if rows and rows[0][0] else None
    refreshed_at, refresh_ok, detail, stale = None, None, "", False
    if table_exists(con, META_SCHEMA, "runs"):
        last = con.execute(
            f"SELECT finished_at, ok, coalesce(detail, '') FROM lake.{META_SCHEMA}.runs "
            "WHERE command = 'refresh' ORDER BY started_at DESC LIMIT 1"
        ).fetchall()
        if last:
            refreshed_at, refresh_ok, detail = last[0]
        if table_exists(con, META_SCHEMA, "staged_units"):
            stale = bool(
                con.execute(
                    f"""
                    SELECT coalesce(
                        max(staged_at) > (
                            SELECT max(finished_at) FROM lake.{META_SCHEMA}.runs
                            WHERE command IN ('curate', 'refresh') AND ok
                        ), false)
                    FROM lake.{META_SCHEMA}.staged_units
                    """
                ).fetchall()[0][0]
            )
    return Currency(through, refreshed_at, refresh_ok, detail, stale)


def currency_line(c: Currency) -> str:
    through = f"games through {c.through}" if c.through else "no catalog yet"
    if c.refreshed_at is None:
        refresh = "no refresh recorded"
    elif c.refresh_ok:
        refresh = f"refreshed {c.refreshed_at:%Y-%m-%d %H:%M}"
    else:
        why = f": {c.detail}" if c.detail else ""
        refresh = f"last refresh {c.refreshed_at:%Y-%m-%d %H:%M} FAILED{why}"
    stale = ". Staged since the last curate, run nbalake curate" if c.staged_since_curate else ""
    return f"lake: {through}, {refresh}{stale}"


def _require_catalog(con: duckdb.DuckDBPyConnection) -> None:
    if not table_exists(con, META_SCHEMA, "catalog"):
        raise LookupError("the lake has no catalog yet. Run: nbalake curate")


def _scratch(con: duckdb.DuckDBPyConnection) -> list[TableInfo]:
    saved = dict(_provenance(con))
    rows = con.execute(
        f"SELECT table_name, estimated_size FROM duckdb_tables() "
        f"WHERE database_name = '{SCRATCH}' AND table_name <> '{PROVENANCE}' ORDER BY 1"
    ).fetchall()
    return [
        TableInfo(SCRATCH, n, TableKind.SCRATCH, r, saved_note(saved[n]) if n in saved else "")
        for n, r in rows
    ]


@dataclass(frozen=True, slots=True)
class Provenance:
    sql: str
    rows: int
    created_at: datetime


def _provenance(con: duckdb.DuckDBPyConnection) -> list[tuple[str, Provenance]]:
    if not table_exists(con, "main", PROVENANCE, database=SCRATCH):
        return []
    rows = con.execute(f"SELECT name, sql, rows, created_at FROM {SCRATCH}.{PROVENANCE}").fetchall()
    return [(n, Provenance(q, r, at)) for n, q, r, at in rows]


def saved_note(p: Provenance) -> str:
    return f"Saved by nba sql --out at {p.created_at:%Y-%m-%d %H:%M} UTC, {p.rows:,} rows."


def inventory(con: duckdb.DuckDBPyConnection) -> list[TableInfo]:
    _require_catalog(con)
    license_column = "license" if _catalog_has(con, "license") else "'open'"
    rows = con.execute(
        f"""
        SELECT schema, name, kind, rows, description, rows_from, grain, partition, sort,
               coverage, {license_column}
        FROM lake.{META_SCHEMA}.catalog ORDER BY schema, name
        """
    ).fetchall()
    return [
        TableInfo(
            schema=s,
            name=n,
            kind=TableKind(k),
            rows=r,
            description=d or "",
            rows_from=rf,
            grain=tuple(g),
            partition=p,
            sort=tuple(so),
            coverage=tuple(Season(c["season"], c["rows"]) for c in cov),
            license=lic,
        )
        for s, n, k, r, d, rf, g, p, so, cov, lic in rows
    ] + _scratch(con)


def matches(qualified: str, pattern: str) -> bool:
    if any(ch in pattern for ch in "*?["):
        return fnmatch.fnmatchcase(qualified, pattern.lower())
    return pattern.lower() in qualified


def _schema_line(schema: str, members: list[TableInfo]) -> TableInfo:
    seasons = sorted({c for t in members for c in t.coverage}, key=lambda c: c.season)
    span = (Season(seasons[0].season, 0), Season(seasons[-1].season, 0)) if seasons else ()
    return TableInfo(
        schema,
        "*",
        TableKind.STAGED,
        sum(t.rows or 0 for t in members),
        f"{len(members)} staged source tables, listed by: nba tables '{schema}.*'",
        coverage=span,
    )


def tables(con: duckdb.DuckDBPyConnection, pattern: str | None = None) -> list[TableInfo]:
    found = inventory(con)
    if pattern is not None:
        return [t for t in found if matches(t.qualified, pattern)]
    listed = [t for t in found if t.schema in (CURATED, SCRATCH)]
    for schema in sorted({t.schema for t in found} - {CURATED, SCRATCH}):
        listed.append(_schema_line(schema, [t for t in found if t.schema == schema]))
    return listed


def qualify(name: str) -> str:
    return name.lower() if "." in name else f"{CURATED}.{name.lower()}"


def nearest(names: list[str], name: str, n: int = 3) -> list[str]:
    by_table = {q.partition(".")[2]: q for q in names}
    close = difflib.get_close_matches(qualify(name), names, n=n, cutoff=0.6)
    close += [by_table[t] for t in difflib.get_close_matches(name.split(".")[-1], by_table, n=n)]
    return list(dict.fromkeys(close))[:n]


def unknown_table(names: list[str], name: str) -> LookupError:
    hint = nearest(names, name)
    suggestion = f" Did you mean {', '.join(hint)}?" if hint else ""
    return LookupError(f"no table {qualify(name)}.{suggestion} List tables with: nba tables")


def _catalog_columns(con: duckdb.DuckDBPyConnection, table: TableInfo) -> tuple[ColumnInfo, ...]:
    rows = con.execute(
        f"""
        SELECT column_name, type, null_percent, min, max, "distinct", top, example
        FROM lake.{META_SCHEMA}.catalog_columns WHERE schema = ? AND name = ? ORDER BY ordinal
        """,
        [table.schema, table.name],
    ).fetchall()
    return tuple(
        ColumnInfo(c, t, np, lo, hi, d, tuple(Value(v["value"], v["rows"]) for v in top or ()), ex)
        for c, t, np, lo, hi, d, top, ex in rows
    )


def _scratch_columns(con: duckdb.DuckDBPyConnection, table: TableInfo) -> tuple[ColumnInfo, ...]:
    rows = con.execute(f'DESCRIBE {SCRATCH}."{table.name}"').fetchall()
    return tuple(ColumnInfo(c, t) for c, t, *_ in rows)


def describe(con: duckdb.DuckDBPyConnection, name: str) -> TableDoc:
    found = {t.qualified: t for t in inventory(con)}
    table = found.get(qualify(name))
    if table is None:
        raise unknown_table(list(found), name)
    match table.kind:
        case TableKind.SCRATCH:
            saved = dict(_provenance(con)).get(table.name)
            made = Lineage(sql=saved.sql if saved else None)
            return TableDoc(table, _scratch_columns(con, table), lineage=made)
        case TableKind.TABLE | TableKind.VIEW | TableKind.SEED | TableKind.STAGED:
            notes = tuple(c for c in caveats() if c.table == table.qualified)
            by_type = type_coverage(con, (table.qualified,)).get(table.qualified, ())
            return TableDoc(
                table, _catalog_columns(con, table), notes, lineage(con, table), by_type
            )


def type_coverage(
    con: duckdb.DuckDBPyConnection, tables: Sequence[str]
) -> dict[str, tuple[TypeCoverage, ...]]:
    """Each table's seasons per season_type as the last curate counted them, earliest type first."""
    if not tables or not table_exists(con, META_SCHEMA, "catalog_coverage"):
        return {}
    rows = con.execute(
        f"""
        SELECT schema || '.' || name AS t, season_type,
               list(struct_pack(season, rows) ORDER BY season) AS seasons
        FROM lake.{META_SCHEMA}.catalog_coverage
        WHERE season_type IS NOT NULL AND list_contains($tables, schema || '.' || name)
        GROUP BY 1, 2
        ORDER BY 1, min(season), 2
        """,
        {"tables": list(tables)},
    ).fetchall()
    out: dict[str, list[TypeCoverage]] = {}
    for t, season_type, seasons in rows:
        out.setdefault(t, []).append(
            TypeCoverage(season_type, tuple(Season(c["season"], c["rows"]) for c in seasons))
        )
    return {t: tuple(v) for t, v in out.items()}


def _catalog_has(con: duckdb.DuckDBPyConnection, column: str) -> bool:
    return bool(
        con.execute(
            "SELECT count(*) FROM duckdb_columns() WHERE database_name = 'lake' "
            "AND schema_name = ? AND table_name = 'catalog' AND column_name = ?",
            [META_SCHEMA, column],
        ).fetchall()[0][0]
    )


def lineage(con: duckdb.DuckDBPyConnection, table: TableInfo) -> Lineage:
    if table.kind is TableKind.STAGED:
        dataset = datasets.BY_NAME.get(table.qualified)
        units = con.execute(
            f"SELECT count(*) FROM lake.{META_SCHEMA}.staged_units WHERE dataset = ?",
            [table.qualified],
        ).fetchall()[0][0]
        return Lineage(upstream=upstream(dataset.fetch) if dataset else None, units=int(units))
    if not _catalog_has(con, "gates"):
        return Lineage()
    sources, gates = con.execute(
        f"SELECT sources, gates FROM lake.{META_SCHEMA}.catalog WHERE schema = ? AND name = ?",
        [table.schema, table.name],
    ).fetchall()[0]
    latest = dict(
        con.execute(
            f"SELECT gate, violations FROM lake.{META_SCHEMA}.gate_results "
            "QUALIFY row_number() OVER (PARTITION BY gate ORDER BY checked_at DESC) = 1"
        ).fetchall()
    )
    return Lineage(tuple(sources), tuple(GateStatus(g, latest.get(g)) for g in gates))


def upstream(fetch: Fetch) -> str:
    match fetch:
        case ReleaseAssets(tag=tag, repo=repo):
            return f"github.com/{repo} release {tag}"
        case GitDir(repo=repo, path=path, ref=ref):
            return f"github.com/{repo} {ref}:{path}"
        case GitTree(repo=repo, ref=ref):
            return f"github.com/{repo} {ref}"
        case Kaggle(owner=owner, slug=slug):
            return f"kaggle {owner}/{slug}"
        case DropFolder(vendor=vendor):
            return f"hand-downloaded files in drop/{vendor}"


def first_sentence(text: str) -> str:
    head, dot, _ = text.partition(". ")
    return head + "." if dot else text


def coverage_runs(coverage: tuple[Season, ...]) -> str:
    """Contiguous season runs with the row range, e.g. '1997-2026 (30 seasons, 2 to 9 rows)'."""
    if not coverage:
        return "no season column"
    runs: list[list[int]] = []
    for c in coverage:
        if runs and c.season == runs[-1][-1] + 1:
            runs[-1].append(c.season)
        else:
            runs.append([c.season])
    spans = ", ".join(str(r[0]) if len(r) == 1 else f"{r[0]}-{r[-1]}" for r in runs)
    lo, hi = min(c.rows for c in coverage), max(c.rows for c in coverage)
    return f"{spans} ({len(coverage)} seasons, {lo:,} to {hi:,} rows each)"


@dataclass(frozen=True, slots=True)
class Caveat:
    table: str
    column: str | None
    seasons: str
    note: str

    @property
    def subject(self) -> str:
        return f"{self.table}.{self.column}" if self.column else self.table


def caveats() -> tuple[Caveat, ...]:
    text = (resources.files("nbalake") / "sql" / "seed" / "caveats.csv").read_text("utf-8")
    return tuple(
        Caveat(r["table_name"], r["column_name"] or None, r["seasons"], r["note"])
        for r in csv.DictReader(io.StringIO(text))
    )


def read_tables(con: duckdb.DuckDBPyConnection, sql: str) -> frozenset[str]:
    """Tables the SQL reads, with each macro call and curated view expanded to what it reads."""
    bodies = {m.name: m.body for m in macros.shipped()}
    bodies |= {
        f"{CURATED}.{s.model.name}": s.sql for s in shipped_steps() if s.model.kind is Kind.VIEW
    }
    found: set[str] = set()
    pending, seen = [sql], set[str]()
    while pending:
        rel = fingerprint.relations(con, pending.pop())
        found.update(rel.tables)
        called = [r for r in (*rel.functions, *rel.tables) if r in bodies and r not in seen]
        seen.update(called)
        pending += [bodies[r] for r in called]
    return frozenset(found)


def query_caveats(
    con: duckdb.DuckDBPyConnection, sql: str, columns: Sequence[str]
) -> tuple[Caveat, ...]:
    """Every table-level caveat of a table the query reads, and a column-level one only when
    the query text or its result names the column."""
    try:
        tables = read_tables(con, sql)
    except ValueError:
        return ()
    words = set(re.findall(r"\w+", sql.lower())) | {c.lower() for c in columns}
    return tuple(
        c
        for c in caveats()
        if c.table in tables and (c.column is None or c.column.lower() in words)
    )


def personal_reads(con: duckdb.DuckDBPyConnection, queries: Sequence[str]) -> tuple[str, ...]:
    """The personal-use tables the queries read, macros and views expanded, sorted."""
    if not _catalog_has(con, "license"):
        return ()
    personal = {
        f"{s}.{n}"
        for s, n in con.execute(
            f"SELECT schema, name FROM lake.{META_SCHEMA}.catalog WHERE license = 'personal'"
        ).fetchall()
    }
    read: set[str] = set()
    for sql in queries:
        read |= read_tables(con, sql)
    return tuple(sorted(read & personal))


class HitKind(Enum):
    TABLE = "table"
    COLUMN = "column"
    CAVEAT = "caveat"
    MACRO = "macro"
    METRIC = "metric"


@dataclass(frozen=True, slots=True)
class Hit:
    kind: HitKind
    name: str
    detail: str


def search(con: duckdb.DuckDBPyConnection, term: str) -> list[Hit]:
    """Curated tables and columns, then metrics, macros, caveats, and staged tables and columns."""
    _require_catalog(con)
    like = f"%{term.lower()}%"
    found = con.execute(
        f"""
        SELECT schema = '{CURATED}' AS curated, 'table', schema || '.' || name, description
        FROM lake.{META_SCHEMA}.catalog
        WHERE lower(name) LIKE $like OR lower(description) LIKE $like
        UNION ALL
        SELECT schema = '{CURATED}', 'column', schema || '.' || name || '.' || column_name, type
        FROM lake.{META_SCHEMA}.catalog_columns WHERE lower(column_name) LIKE $like
        ORDER BY 1 DESC, 2 DESC, 3
        """,
        {"like": like},
    ).fetchall()
    hits = [(c, Hit(HitKind(k), n, first_sentence(d or ""))) for c, k, n, d in found]
    needle = term.lower()
    notes = [
        Hit(HitKind.CAVEAT, c.subject, c.note)
        for c in caveats()
        if needle in f"{c.subject} {c.note}".lower()
    ]
    measured = [
        Hit(HitKind.METRIC, m.name, m.summary)
        for m in metrics.registered()
        if needle in f"{m.name} {m.summary}".lower()
    ]
    domain = [
        Hit(HitKind.MACRO, m.signature, m.description)
        for m in macros.shipped()
        if needle in f"{m.name} {m.description}".lower()
    ]
    return [h for c, h in hits if c] + measured + domain + notes + [h for c, h in hits if not c]


STOPWORDS = frozenset(
    {"a", "an", "and", "by", "for", "in", "nba", "of", "on", "per", "season", "seasons", "the"}
)
TYPE_ALIASES = {"postseason": "playoffs"}


@dataclass(frozen=True, slots=True)
class ConceptCoverage:
    words: tuple[str, ...]
    season_types: tuple[str, ...]
    tables: tuple[tuple[str, tuple[TypeCoverage, ...]], ...]

    def earliest(self, season_type: str) -> tuple[int, str] | None:
        firsts = [
            (c.seasons[0].season, t)
            for t, cov in self.tables
            for c in cov
            if c.season_type == season_type and c.seasons
        ]
        return min(firsts) if firsts else None


def _curated_season_types(con: duckdb.DuckDBPyConnection) -> list[str]:
    if not table_exists(con, META_SCHEMA, "catalog_coverage"):
        return []
    rows = con.execute(
        f"SELECT DISTINCT season_type FROM lake.{META_SCHEMA}.catalog_coverage "
        f"WHERE schema = '{CURATED}' AND season_type IS NOT NULL ORDER BY 1"
    ).fetchall()
    return [t for (t,) in rows]


def _names_type(word: str, season_types: list[str]) -> str | None:
    word = TYPE_ALIASES.get(word, word)
    for t in season_types:
        if word == t or (len(word) >= 4 and t.startswith(word)) or word in t.split("-"):
            return t
    return None


def _tables_matching(con: duckdb.DuckDBPyConnection, word: str) -> set[str]:
    stem = word[:-1] if len(word) > 3 and word.endswith("s") else word
    rows = con.execute(
        f"""
        SELECT schema || '.' || name FROM lake.{META_SCHEMA}.catalog
        WHERE schema = '{CURATED}' AND (lower(name) LIKE $like OR lower(description) LIKE $like)
        UNION
        SELECT schema || '.' || name FROM lake.{META_SCHEMA}.catalog_columns
        WHERE schema = '{CURATED}' AND lower(column_name) LIKE $like
        """,
        {"like": f"%{stem}%"},
    ).fetchall()
    return {t for (t,) in rows}


def concept_coverage(con: duckdb.DuckDBPyConnection, term: str) -> ConceptCoverage:
    _require_catalog(con)
    known = _curated_season_types(con)
    words: list[str] = []
    named: list[str] = []
    for w in re.findall(r"[\w-]+", term.lower()):
        if w in STOPWORDS:
            continue
        season_type = _names_type(w, known)
        if season_type is not None:
            named.append(season_type)
        else:
            words.append(w)
    matched: list[str] = []
    if words:
        common = _tables_matching(con, words[0])
        for w in words[1:]:
            common &= _tables_matching(con, w)
        matched = sorted(common)
    by_table = type_coverage(con, matched)
    tables = tuple((t, by_table.get(t, ())) for t in matched)
    return ConceptCoverage(tuple(words), tuple(dict.fromkeys(named)), tables)
