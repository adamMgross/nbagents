from __future__ import annotations

import contextlib
import dataclasses
import functools
import importlib.util
import json
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Annotated

import duckdb
import typer

from nbalake import lake
from nbalake.explore import catalog, entities, macros, metrics, script, session, skills
from nbalake.explore import query as q
from nbalake.explore.guide import render_guide
from nbalake.explore.render import Format, render
from nbalake.report import render as report_render
from nbalake.report import spec as report_spec
from nbalake.runtime import Runtime

app = typer.Typer(
    name="nba",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    rich_markup_mode=None,
    help="Explore the NBA lake, read only. Start with: nba guide",
)

RootOpt = Annotated[
    str | None, typer.Option("--root", envvar="NBALAKE_ROOT", help="Lake directory.")
]
FormatOpt = Annotated[
    Format, typer.Option("--format", "-f", help="Output format: md, jsonl, csv, or table.")
]
RawOpt = Annotated[
    bool, typer.Option("--raw", help="Print full cells and floats, no 80-character cut.")
]
TimeoutOpt = Annotated[float, typer.Option("--timeout", help="Seconds before the query stops.")]
AllowSpillOpt = Annotated[
    str | None,
    typer.Option(
        "--allow-spill",
        metavar="SIZE",
        help="Raise the 4GB spill cap to SIZE (like 12GB) for this run. Ask the owner first.",
    ),
]

EXPECTED = (duckdb.Error, LookupError, ValueError, FileNotFoundError, q.QueryTimeout)


POLARS_MISSING = {
    Runtime.REPO: "nba py needs polars. Install it with: uv sync --extra analysis",
    Runtime.APP: "nba py is not in the installed app. Use nba sql with --out for each step.",
}


def guarded[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except duckdb.OutOfMemoryException:
            typer.echo(f"error: {session.OVER_CAP}", err=True)
            raise typer.Exit(1) from None
        except EXPECTED as e:
            typer.echo(f"error: {str(e).strip()}", err=True)
            raise typer.Exit(1) from None

    return wrapper


def notice(text: str) -> None:
    typer.echo(text, err=True)


def connect(
    ctx: typer.Context, root: str | None, *, scratch: bool = False, allow_spill: str | None = None
) -> duckdb.DuckDBPyConnection:
    con = session.connect(lake.Root.resolve(root), scratch=scratch, allow_spill=allow_spill)
    ctx.call_on_close(con.close)
    return con


def announce_currency(con: duckdb.DuckDBPyConnection) -> None:
    notice(catalog.currency_line(catalog.currency(con)))


@app.command()
def guide(ctx: typer.Context, root: RootOpt = None) -> None:
    """Print the orientation an agent needs before its first query.

    Covers the workflow, every command with an example, the id and season
    conventions, the output contract, and the caveats that most often cause
    a wrong answer. The same text is the nba-lake skill.

    \b
    Examples:
      nba guide
    """
    with contextlib.suppress(duckdb.Error, LookupError, FileNotFoundError):
        announce_currency(connect(ctx, root))
    typer.echo(render_guide(skills.target(Runtime.current())), nl=False)


@app.command()
@guarded
def tables(
    ctx: typer.Context,
    pattern: Annotated[
        str | None,
        typer.Argument(help="Substring, or a glob like 'sdv.*shot*'. Default: curated tables."),
    ] = None,
    fmt: FormatOpt = Format.MD,
    raw: RawOpt = False,
    root: RootOpt = None,
) -> None:
    """List tables, one line each, with kind, rows, seasons, grain, and description.

    With no pattern, lists the curated nba.* tables and your scratch tables,
    plus one line per staged source schema. A pattern without wildcards
    matches anywhere in schema.table.

    \b
    Examples:
      nba tables
      nba tables shot
      nba tables 'sdv.leaguedash_*'
      nba tables scratch.
    """
    con = connect(ctx, root, scratch=lake.Root.resolve(root).scratch.exists())
    announce_currency(con)
    found = catalog.tables(con, pattern)
    if not found:
        notice(f"no table matches {pattern!r}. Try a shorter pattern.")
        return
    rows = [
        (
            t.qualified,
            t.kind.value,
            t.rows,
            t.seasons,
            ", ".join(t.grain),
            ("(personal use) " if t.license == "personal" else "")
            + catalog.first_sentence(t.description),
        )
        for t in found
    ]
    header = ("table", "kind", "rows", "seasons", "grain", "description")
    typer.echo(render(header, rows, fmt, raw=True))


@app.command()
@guarded
def describe(
    ctx: typer.Context,
    table: Annotated[str, typer.Argument(help="schema.table, or a bare name for nba.*")],
    word: Annotated[
        str | None,
        typer.Argument(metavar="[COLUMNS]", help="Show only columns whose name contains this."),
    ] = None,
    columns_only: Annotated[
        bool,
        typer.Option("--columns", help="Print only name, type, nulls, and range per column."),
    ] = False,
    fmt: FormatOpt = Format.MD,
    root: RootOpt = None,
) -> None:
    """Show one table: what it holds, its size, coverage, caveats, and columns.

    Read this before querying a table you have not used in this session.
    Curated tables show what they are built from, how many gates check them
    and whether those passed at the last curate, and each column's null
    rate, range or top values, distinct count, and an example. Staged
    tables show their upstream release and units, and types. Scratch
    tables show types.
    Wide tables have over 100 columns, so pass a word to list only the
    columns that contain it.

    \b
    Examples:
      nba describe nba.shots
      nba describe player_box
      nba describe player_seasons x3p
      nba describe player_box --columns
      nba describe scratch.top_scorers
    """
    con = connect(ctx, root, scratch=table.lower().startswith(session.SCRATCH))
    announce_currency(con)
    doc = catalog.describe(con, table)
    if word is not None:
        kept = tuple(c for c in doc.columns if word.lower() in c.name.lower())
        doc = dataclasses.replace(doc, columns=kept)
    if columns_only:
        rows = [(c.name, c.type, _nulls(c.null_percent), _values(c)) for c in doc.columns]
        typer.echo(render(("column", "type", "nulls", "range or top values"), rows, fmt))
        return
    if fmt is not Format.MD:
        rows = [
            (c.name, c.type, c.null_percent, c.min, c.max, c.distinct, c.example)
            for c in doc.columns
        ]
        header = ("column", "type", "null_percent", "min", "max", "distinct", "example")
        typer.echo(render(header, rows, fmt))
        return
    typer.echo(describe_md(doc))


def describe_md(doc: catalog.TableDoc) -> str:
    t = doc.table
    rows = "not counted" if t.rows is None else f"{t.rows:,}"
    if t.rows_from:
        rows += f" (counted from {t.rows_from})"
    facts = [f"rows: {rows}", f"seasons: {catalog.coverage_runs(t.coverage)}"]
    facts += [f"{c.season_type}: {catalog.coverage_runs(c.seasons)}" for c in doc.by_type]
    if t.grain:
        facts.append("grain: one row per " + ", ".join(t.grain))
    if t.license == "personal":
        facts.append("license: personal use only, do not share")
    if t.partition:
        facts.append(f"partitioned by {t.partition}")
    if t.sort:
        facts.append("sorted by " + ", ".join(t.sort))
    if doc.joins:
        facts.append("joins: " + ", ".join(f"{c} -> {target}" for c, target in doc.joins))
    facts += lineage_facts(doc.lineage)
    lines = [f"# {t.qualified} ({t.kind.value})", ""]
    if t.description:
        lines += [t.description, ""]
    lines += [f"- {f}" for f in facts]
    if doc.lineage.sql is not None:
        lines += ["", "Made by:", "", *("    " + ln for ln in doc.lineage.sql.splitlines())]
    if doc.caveats:
        lines += ["", "Caveats:", ""]
        lines += [f"- {c.subject} ({c.seasons}): {c.note}" for c in doc.caveats]
    if any(c.min is not None or c.example is not None for c in doc.columns):
        cols = [
            (c.name, c.type, _nulls(c.null_percent), _values(c), c.distinct, c.example)
            for c in doc.columns
        ]
        header = ("column", "type", "nulls", "range or top values", "distinct", "example")
    else:
        cols = [(c.name, c.type) for c in doc.columns]
        header = ("column", "type")
    lines += ["", render(header, cols, Format.MD)]
    return "\n".join(lines)


def lineage_facts(lin: catalog.Lineage) -> list[str]:
    facts: list[str] = []
    if lin.upstream is not None:
        facts.append(f"upstream: {lin.upstream}")
    if lin.units is not None:
        facts.append(f"units staged: {lin.units:,}")
    if lin.sources:
        facts.append("built from: " + ", ".join(lin.sources))
    if lin.gates:
        failing = [g for g in lin.gates if g.violations]
        unchecked = [g for g in lin.gates if g.violations is None]
        if failing:
            status = "failing at the last curate: " + ", ".join(
                f"{g.name} ({g.violations:,} violations)" for g in failing
            )
        elif unchecked:
            status = f"{len(unchecked)} not yet checked"
        else:
            status = "all pass at the last curate"
        facts.append(f"gates: {len(lin.gates)}, {status}")
    return facts


def _nulls(pct: float | None) -> str:
    if pct is None:
        return ""
    if pct == 0:
        return "0"
    return "<0.1%" if pct < 0.1 else f"{pct:.1f}%"


def _values(c: catalog.ColumnInfo) -> str:
    if c.top:
        return ", ".join(f"{v.value} ({v.rows:,})" for v in c.top)
    if c.min is None:
        return ""
    return c.min if c.min == c.max else f"{c.min} to {c.max}"


@app.command()
@guarded
def search(
    ctx: typer.Context,
    term: Annotated[str, typer.Argument(help="A word to look for, like rebound or elo.")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Hits to print.")] = 50,
    fmt: FormatOpt = Format.MD,
    root: RootOpt = None,
) -> None:
    """Find where a word appears: tables, descriptions, columns, metrics, macros, and caveats.

    Matches are case-insensitive substrings. Curated tables and columns come
    first, then metrics, macros, and caveats, then staged source tables and columns. Use it when
    you do not know which table holds a stat. When nothing matches the whole
    phrase, it lists the curated tables matching every word with their
    seasons, per season type when a word names one, like playoff.

    \b
    Examples:
      nba search rebound
      nba search elo
      nba search spread -n 10
    """
    con = connect(ctx, root)
    hits = catalog.search(con, term)
    rows = [(h.kind.value, h.name, h.detail) for h in hits[:limit]]
    if not rows:
        notice(f"nothing matches {term!r} as one phrase. Each word apart, in curated tables:")
        print_concept(catalog.concept_coverage(con, term), fmt)
        return
    typer.echo(render(("kind", "name", "detail"), rows, fmt, raw=True))
    if len(hits) > limit:
        notice(f"showing {limit} of {len(hits)} hits. Use a longer word or raise --limit.")


def print_concept(cc: catalog.ConceptCoverage, fmt: Format) -> None:
    what = " ".join(cc.words)
    if not cc.words or not cc.tables:
        notice(f"no curated table matches every word of {what!r}. Try fewer words or nba tables.")
        return
    rows: list[tuple[str, str, str]] = []
    for t, by_type in cc.tables:
        shown = [c for c in by_type if not cc.season_types or c.season_type in cc.season_types]
        if not by_type:
            rows.append((t, "", "no season_type column"))
        elif not shown:
            rows.append((t, ", ".join(cc.season_types), "none"))
        rows += [(t, c.season_type, catalog.coverage_runs(c.seasons)) for c in shown]
    typer.echo(render(("table", "season_type", "seasons"), rows, fmt, raw=True))
    for season_type in cc.season_types:
        first = cc.earliest(season_type)
        if first is None:
            notice(f"no curated table matching {what!r} has {season_type} rows.")
        else:
            notice(
                f"no curated table matching {what!r} has {season_type} rows before "
                f"{first[0]} ({first[1]}). Staged tables keep their source's season types."
            )


@app.command()
@guarded
def coverage(
    ctx: typer.Context,
    subject: Annotated[
        str, typer.Argument(help="A table, like player_box, or words, like 'playoff minutes'.")
    ],
    fmt: FormatOpt = Format.MD,
    root: RootOpt = None,
) -> None:
    """Say from which season, and for which season types, a table or a concept has rows.

    A table prints its seasons per season type, or all of them when it has
    no season_type column. Words print every curated table that matches all
    of them, with the earliest season for any season type the words name,
    so an absence is as answerable as a presence.

    \b
    Examples:
      nba coverage player_box
      nba coverage 'playoff minutes'
      nba coverage 'play-in elo'
    """
    con = connect(ctx, root)
    found = {t.qualified: t for t in catalog.inventory(con)}
    table = found.get(catalog.qualify(subject)) if " " not in subject.strip() else None
    if table is None:
        print_concept(catalog.concept_coverage(con, subject), fmt)
        return
    by_type = catalog.type_coverage(con, (table.qualified,)).get(table.qualified, ())
    rows = [(c.season_type, catalog.coverage_runs(c.seasons)) for c in by_type]
    rows = rows or [("all", catalog.coverage_runs(table.coverage))]
    typer.echo(render(("season_type", "seasons"), rows, fmt, raw=True))


@app.command()
@guarded
def find(
    ctx: typer.Context,
    kind: Annotated[entities.EntityKind, typer.Argument(help="player, team, or game")],
    text: Annotated[str, typer.Argument(help="A name, nickname, or words that describe a game.")],
    limit: Annotated[int, typer.Option("--limit", "-n", help="Candidates to print.")] = 20,
    fmt: FormatOpt = Format.MD,
    root: RootOpt = None,
) -> None:
    """Turn a name into an id. Prints every candidate when the text is ambiguous.

    Matching tries, in order: the exact name, a known alias or nickname,
    every word of the text appearing in the name or its aliases, word
    prefixes, then Jaro-Winkler above 0.9. Accents and punctuation are
    ignored. Use the id in SQL, never the name.

    A team is one team_id across moves and renames, so every name it used is
    listed with its seasons. A game is found by words of its label and
    aliases: the date, both team names or codes, the season (2015 16), the
    round, and the game number.

    \b
    Examples:
      nba find player 'stephen curry'
      nba find player steph
      nba find player 'larry johnson'
      nba find team sonics
      nba find game 'finals 2016 game 7'
      nba find game 'warriors cavaliers 2016-06-19'
    """
    match = entities.find(connect(ctx, root), kind, text)
    if not match.candidates:
        raise LookupError(f"no {kind.value} matches {text!r}. Try fewer or shorter words.")
    shown = match.candidates[:limit]
    rows = [(e.id, e.label, _seasons(e.season_min, e.season_max), e.context) for e in shown]
    typer.echo(render(("id", "name", "seasons", "context"), rows, fmt))
    assert match.tier is not None
    if match.resolved is None:
        ids = len({e.id for e in match.candidates})
        more = f", showing {limit}" if len(match.candidates) > limit else ""
        notice(
            f"{ids} {kind.value}s match {text!r} ({match.tier.name.lower()}{more}). "
            "Add words to narrow it, or pick one by id."
        )


def _seasons(lo: int | None, hi: int | None) -> str:
    if lo is None:
        return ""
    return str(lo) if lo == hi else f"{lo}-{hi}"


@app.command()
@guarded
def sql(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="One DuckDB query against the lake.")],
    out: Annotated[
        str | None,
        typer.Option("--out", help="Keep every row in scratch.<name> and print the count."),
    ] = None,
    explain: Annotated[
        bool,
        typer.Option(
            "--explain", help="Run it, discard the rows, print files read, rows, and the plan."
        ),
    ] = False,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Rows to print.")] = 50,
    fmt: FormatOpt = Format.MD,
    raw: RawOpt = False,
    timeout: TimeoutOpt = 60.0,
    allow_spill: AllowSpillOpt = None,
    root: RootOpt = None,
) -> None:
    """Run one DuckDB query, read only, and print at most --limit rows.

    Tables are nba.* (curated), the staged source schemas, meta.*, and
    scratch.* (yours, writable). When more rows exist than --limit, stderr
    says so. --out <name> stores the whole result as scratch.<name> and
    prints its row count and columns instead of rows. A session has 4GB of
    memory and 4GB of disk spill, and a query past either stops with a
    message saying how to narrow it. --explain runs the query under the same
    caps and prints the Parquet files it read, the rows each table gave,
    and the plan, without rows. Files read is the cost: check it before
    --out or a longer --timeout.

    \b
    Examples:
      nba sql "from nba.games where season = 2016 and season_type = 'playoffs'"
      nba sql "select season, avg(pts) from nba.team_games group by 1 order by 1" -n 100
      nba sql "from nba.player_box where player_id = 201939" --out curry_games
      nba sql "from nba.pbp where season = 2016 and game_id = '0041500407'" --explain
      nba sql "drop table scratch.curry_games"
    """
    con = connect(
        ctx,
        root,
        scratch=out is not None or session.needs_scratch(query),
        allow_spill=allow_spill,
    )
    if explain:
        if out is not None:
            raise ValueError("--explain discards rows, so it cannot be combined with --out")
        typer.echo(explain_text(q.explain(con, query, timeout=timeout)))
        return
    if out is not None:
        saved = q.save(con, query, out, timeout=timeout)
        typer.echo(f"{saved.name}: {saved.rows:,} rows")
        typer.echo(render(("column", "type"), saved.columns, Format.MD))
        warn_caveats(catalog.query_caveats(con, query, [c for c, _ in saved.columns]))
        return
    result = q.run(con, query, limit=limit, timeout=timeout)
    if result is None:
        notice("ok")
        return
    if result.columns[:1] == ("explain_key",):
        typer.echo("\n".join(str(row[-1]).rstrip("\n") for row in result.rows))
        return
    typer.echo(render(result.columns, result.rows, fmt, raw=raw))
    if result.truncated:
        notice(q.truncation_notice(limit))
    elif not result.rows:
        notice("no rows")
    warn_caveats(catalog.query_caveats(con, query, result.columns))


CAVEAT_LINES = 4


def caveat_lines(found: Sequence[catalog.Caveat]) -> list[str]:
    lines = [f"caveat {c.subject} ({c.seasons}): {c.note}" for c in found[:CAVEAT_LINES]]
    if len(found) > CAVEAT_LINES:
        tables = " ".join(sorted({c.table for c in found[CAVEAT_LINES:]}))
        lines.append(f"{len(found) - CAVEAT_LINES} more caveats: nba describe {tables}")
    return lines


def warn_caveats(found: Sequence[catalog.Caveat]) -> None:
    for line in caveat_lines(found):
        notice(line)


def explain_text(e: q.Explained) -> str:
    lines = [f"files read: {e.files_read}"]
    lines += [f"rows from {table}: {rows:,}" for table, rows in e.rows_by_table().items()]
    lines += [f"elapsed: {e.seconds:.2f}s, {e.bytes_read / 1e6:,.1f} MB read", "", e.plan]
    return "\n".join(lines)


@app.command()
@guarded
def py(
    ctx: typer.Context,
    path: Annotated[str, typer.Argument(help="A Python file, or - to read the script from stdin.")],
    timeout: Annotated[
        float, typer.Option("--timeout", help="Seconds before the script stops.")
    ] = 300.0,
    allow_spill: AllowSpillOpt = None,
    root: RootOpt = None,
) -> None:
    """Run a Python script against the lake for analysis that takes several steps.

    The script gets con (a DuckDB connection with the lake read only, the
    macros loaded, and scratch attached read-write), pl (polars), and duckdb.
    Print what you want to see. Output past 20,000 characters is cut with a
    notice, so print summaries, not whole frames. A traceback shows only the
    script's own lines.

    Keep intermediates in scratch so later steps never rerun an upstream
    query: con.execute("create or replace table scratch.x as ..."). The
    session has the same 4GB memory and 4GB spill caps as nba sql, and the
    script's own Python and polars memory has 4GB more.

    \b
    Examples:
      nba py analysis.py
      nba py - <<'EOF'
      df = con.sql("from player_games(201939, 2016)").pl()
      print(df.select(pl.col("pts").mean()))
      EOF
    """
    if importlib.util.find_spec("polars") is None:
        raise LookupError(POLARS_MISSING[Runtime.current()])
    if path == "-":
        source, filename = typer.get_text_stream("stdin").read(), "<stdin>"
    else:
        with open(path, encoding="utf-8") as f:
            source, filename = f.read(), path
    con = connect(ctx, root, scratch=True, allow_spill=allow_spill)
    result = script.run(con, source, filename, timeout=timeout)
    typer.echo(result.output, nl=False)
    if result.truncated:
        notice(f"output cut at {script.MAX_OUTPUT:,} characters. Print less, or write to scratch.")
    if result.error is not None:
        typer.echo(f"error: {result.error}", err=True)
        raise typer.Exit(1)


@app.command("macros")
def list_macros(fmt: FormatOpt = Format.MD, root: RootOpt = None) -> None:
    """List the domain macros: signature, what each returns, and an example query.

    Macros are DuckDB table macros loaded into every nba sql session. Call
    them in FROM with positional arguments, and optional ones by name.
    Macros you created in scratch are listed last, under yours.

    \b
    Examples:
      nba macros
      nba sql "from player_games(201939, 2016)"
      nba sql "from lineups(NULL, 2016, 500) order by net_rating desc"
    """
    shipped = macros.shipped()
    yours = _scratch_macros(lake.Root.resolve(root))
    if fmt is not Format.MD:
        rows = [(m.name, m.signature, m.description, m.example) for m in shipped]
        rows += [
            (y.signature.partition("(")[0], y.signature, f"yours, a {y.kind} macro in scratch", "")
            for y in yours
        ]
        typer.echo(render(("name", "signature", "description", "example"), rows, fmt, raw=True))
        return
    for m in shipped:
        typer.echo(f'## {m.signature}\n\n{m.description}\n\n    nba sql "{m.example}"\n')
    if yours:
        typer.echo("## yours\n\nMacros in scratch, which persist between sessions.\n")
        for y in yours:
            typer.echo(f"- {y.signature}, {y.kind}: {y.definition}")


@app.command("metrics")
def list_metrics(
    name: Annotated[str | None, typer.Argument(help="A metric whose methodology to print.")] = None,
    fmt: FormatOpt = Format.MD,
) -> None:
    """List the registered metrics, or print one metric's methodology.

    A metric is a settled, versioned definition, like career postseason
    achievement, with a methodology page and table macros that compute it on
    demand. Cite the version beside any number you report from one.

    \b
    Examples:
      nba metrics
      nba metrics career_postseason
      nba sql "from career_postseason() limit 20"
    """
    registered = metrics.registered()
    if name is not None:
        found = next((m for m in registered if m.name == name), None)
        if found is None:
            names = ", ".join(m.name for m in registered)
            typer.echo(f"error: no metric named {name!r}. Registered: {names}.", err=True)
            raise typer.Exit(1)
        typer.echo(found.methodology, nl=False)
        return
    if fmt is not Format.MD:
        rows = [
            (m.name, m.version, m.summary, ", ".join(x.signature for x in m.macros))
            for m in registered
        ]
        typer.echo(render(("name", "version", "summary", "macros"), rows, fmt, raw=True))
        return
    for m in registered:
        typer.echo(f"## {m.name}, version {m.version}\n\n{m.summary}\n")
        for x in m.macros:
            typer.echo(f'- {x.signature}: {x.description}\n\n    nba sql "{x.example}"\n')


@app.command()
@guarded
def report(
    ctx: typer.Context,
    spec_path: Annotated[Path, typer.Argument(help="The report spec, a .json file.")],
    artifact: Annotated[
        Path | None,
        typer.Option(
            "--artifact",
            help="Also write the page without document tags, to publish as an artifact.",
        ),
    ] = None,
    root: RootOpt = None,
) -> None:
    """Render a report spec into one self-contained HTML file beside it.

    A report is the shareable result of an analysis: a finding, tiles, line
    charts and tables from SQL against the lake, and a collapsed account of
    the method and data for a reader who knows nothing about the lake.
    docs/reports.md describes the spec. Write the spec as
    reports/<date>-<slug>.json, render it, and commit both files.

    --artifact writes the same page without its document shell, the form
    the Artifact tool publishes.

    \b
    Examples:
      nba report reports/2026-10-24-best-seasons-since-1974.json
      nba report reports/2026-10-24-best-seasons-since-1974.json --artifact /tmp/page.html
    """
    parsed = report_spec.parse(
        json.loads(spec_path.read_text(encoding="utf-8")), report_spec.load_context()
    )
    con = connect(ctx, root)
    ((through,),) = con.execute(
        "SELECT max(game_date) FROM nba.games WHERE home_pts IS NOT NULL"
    ).fetchall()
    personal = catalog.personal_reads(
        con, [b.sql for b in parsed.blocks if not isinstance(b, report_spec.Text)]
    )
    if personal:
        notice(
            "personal-use data: this report reads "
            + ", ".join(personal)
            + ". Ask the owner before sharing or publishing it."
        )
    meta = report_render.Meta(
        rendered_at=datetime.now().astimezone(),
        lake_through=through,
        metric_versions={m.name: m.version for m in metrics.registered()},
        macros=macros.shipped(),
        personal=personal,
    )
    fragment = report_render.page(parsed, report_render.run(con, parsed), meta)
    out = spec_path.with_suffix(".html")
    out.write_text(report_render.document(fragment), "utf-8")
    typer.echo(str(out))
    if artifact is not None:
        artifact.write_text(fragment, "utf-8")
        typer.echo(str(artifact))


def _scratch_macros(root: lake.Root) -> tuple[macros.ScratchMacro, ...]:
    if not root.scratch.exists():
        return ()
    con = duckdb.connect()
    try:
        session.attach_scratch(con, root)
        return macros.scratch_macros(con, session.SCRATCH)
    finally:
        con.close()


def main() -> None:
    app()
