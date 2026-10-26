from __future__ import annotations

import sys
import threading
import time
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Annotated

import duckdb
import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from nbalake import capture as cap
from nbalake import curate as cur
from nbalake import datasets, lake, preflight
from nbalake import stage as stg
from nbalake import vacuum as vac
from nbalake.explore import catalog, macros, skills
from nbalake.model import Dataset, Unit, Versions
from nbalake.models import ALL as MODELS
from nbalake.runtime import Runtime

app = typer.Typer(no_args_is_help=True, add_completion=False, help="A local NBA data lake.")
console = Console()
err = Console(stderr=True)

RootOpt = Annotated[
    str | None, typer.Option("--root", envvar="NBALAKE_ROOT", help="Lake directory.")
]
Names = Annotated[
    list[str] | None, typer.Argument(help="Dataset names, schemas, or globs. Default: all.")
]


def _root(root: str | None) -> lake.Root:
    return lake.Root.resolve(root)


def _select(names: Sequence[str] | None) -> list[Dataset]:
    try:
        return datasets.select(list(names or ()))
    except KeyError as e:
        err.print(f"[red]{e.args[0]}[/red]")
        raise typer.Exit(2) from None


@contextmanager
def _writing(root: lake.Root, command: str) -> Generator[None]:
    try:
        with lake.writer_lock(root, command):
            yield
    except lake.WriterBusy as e:
        err.print(f"[red]{e}[/red]")
        raise typer.Exit(75) from None


def _connect(root: lake.Root):
    return lake.connect(root, schemas=datasets.SCHEMAS)


@app.command("datasets")
def list_datasets(names: Names = None, root: RootOpt = None) -> None:
    """List registered datasets and how many units each has in raw."""
    store = cap.RawStore(_root(root))
    records = store.records()
    t = Table("dataset", "partition", "raw units", "description", expand=True)
    t.columns[0].no_wrap = True
    t.columns[3].ratio = 3
    t.columns[3].overflow = "fold"
    for d in _select(names):
        n = len(cap.units_in_store(d, records))
        suffix = " Every capture is kept." if d.versions is Versions.ALL else ""
        t.add_row(d.name, d.partition or "", str(n), d.description + suffix)
    console.print(t)


def _capture(
    root: lake.Root, chosen: list[Dataset], jobs: int, limit: int | None
) -> cap.CaptureReport:
    columns = [
        TextColumn("{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeElapsedColumn(),
    ]
    with Progress(*columns, console=console, transient=True) as progress:
        tasks: dict[str, TaskID] = {}
        lock = threading.Lock()
        overall = progress.add_task("[bold]capture", total=None)

        def on_progress(unit: Unit, done: int, total: int | None, finished: bool) -> None:
            with lock:
                if unit.url not in tasks:
                    tasks[unit.url] = progress.add_task(unit.key, total=total)
                progress.update(tasks[unit.url], completed=done, total=total)
                if finished:
                    progress.remove_task(tasks.pop(unit.url))
                    progress.advance(overall)

        return cap.capture(root, chosen, concurrency=jobs, limit=limit, progress=on_progress)


@app.command()
def capture(
    names: Names = None,
    root: RootOpt = None,
    jobs: Annotated[int, typer.Option("-j", "--jobs", help="Concurrent downloads.")] = 8,
    limit: Annotated[int | None, typer.Option(help="Fetch at most this many new units.")] = None,
) -> None:
    """Download every new or changed upstream unit into raw. Never refetches a known version."""
    r = _root(root)
    chosen = _select(names)
    t0 = time.monotonic()
    with _writing(r, "capture"):
        report = _capture(r, chosen, jobs, limit)
    console.print(
        f"fetched {len(report.fetched)} units, {report.bytes / 1e6:,.1f} MB, "
        f"skipped {report.skipped} up to date, {time.monotonic() - t0:,.1f}s"
    )
    _report_failures(report.failed)


class UnitsFailed(Exception):
    def __init__(self, capture: dict[str, str], stage: dict[str, dict[str, str]]) -> None:
        parts: list[str] = []
        if capture:
            parts.append(f"capture failed {len(capture)} units")
        if stage:
            count = sum(len(units) for units in stage.values())
            parts.append(f"stage failed {count} units in {', '.join(sorted(stage))}")
        super().__init__(", ".join(parts))


def _report_failures(failed: dict[str, str]) -> None:
    if failed:
        for k, v in failed.items():
            err.print(f"[red]failed[/red] {k}: {v}")
        raise typer.Exit(1)


def _stage(
    root: lake.Root, con: duckdb.DuckDBPyConnection, chosen: list[Dataset], rebuild: bool = False
) -> stg.StageReport:
    with Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("[bold]stage", total=None)

        def on_unit(ds: Dataset, rec: cap.FetchRecord, rows: int) -> None:
            progress.update(
                task, description=f"[bold]stage[/bold] {ds.name} {rec.key} ({rows:,} rows)"
            )
            progress.advance(task)

        return stg.stage(
            root, con, chosen, rebuild=rebuild, progress=on_unit, registry=datasets.ALL
        )


def _print_stage(report: stg.StageReport) -> None:
    for name in report.retired:
        console.print(f"{name}: dropped, no dataset registers it")
    for name, units in report.loaded.items():
        console.print(f"{name}: loaded {len(units)} units, {sum(u.rows for u in units):,} rows")
    for name, n in report.dropped.items():
        if n:
            console.print(f"{name}: dropped {n} superseded units")
    if report.unchanged:
        console.print(f"unchanged: {len(report.unchanged)} datasets")
    if report.missing:
        console.print(f"[yellow]nothing in raw for[/yellow]: {', '.join(report.missing)}")
    for name, units in report.failed.items():
        key, error = next(iter(units.items()))
        err.print(f"[red]failed[/red] {name}: {len(units)} units, e.g. {key}: {error}")


@app.command()
def stage(
    names: Names = None,
    root: RootOpt = None,
    rebuild: Annotated[
        bool,
        typer.Option(help="Drop the tables first. Use after changing a partition or types."),
    ] = False,
) -> None:
    """Load raw units into source-native tables. Reruns touch only changed units."""
    r = _root(root)
    chosen = _select(names)
    with _writing(r, "stage"):
        con = _connect(r)
        try:
            with lake.run(con, "stage"):
                report = _stage(r, con, chosen, rebuild)
                _print_stage(report)
                if report.failed:
                    raise UnitsFailed({}, report.failed)
        except UnitsFailed:
            raise typer.Exit(1) from None


def _curate(
    con: duckdb.DuckDBPyConnection, run_id: str, enforce_gates: bool, rebuild: bool = False
) -> None:
    try:
        report = cur.curate(
            con,
            run_id=run_id,
            enforce_gates=enforce_gates,
            rebuild=rebuild,
            registry=MODELS,
        )
    except cur.GateFailure as e:
        _print_gates(e.results)
        err.print(f"[red]{e}[/red]; the previous snapshot stays published")
        raise typer.Exit(1) from None
    for name, n in report.rows.items():
        chunks = f", {report.chunks[name]} chunks" if name in report.chunks else ""
        console.print(f"nba.{name}: view" if n is None else f"nba.{name}: {n:,} rows{chunks}")
    if report.skipped:
        console.print(f"unchanged: {len(report.skipped)} models")
    for name in report.retired:
        console.print(f"nba.{name}: dropped, no model registers it")
    _print_gates(report.gates)


def _print_gates(results: list[cur.GateResult]) -> None:
    for g in results:
        mark = "[green]pass[/green]" if g.ok else f"[red]FAIL[/red] {g.violations:,} violations"
        console.print(f"gate {g.gate}: {mark}")
        if not g.ok and g.sample:
            console.print(f"  e.g. {g.sample[0]}")


@app.command()
def curate(
    root: RootOpt = None,
    gates: Annotated[bool, typer.Option(help="Roll back when a quality gate fails.")] = True,
    rebuild: Annotated[
        bool, typer.Option("--rebuild", help="Build every model, changed or not.")
    ] = False,
) -> None:
    """Rebuild the changed nba.* models in one transaction, gated on quality checks.

    A model or chunk is rebuilt when its SQL, layout, the staged units it reads,
    or a curated model it reads changed since the published curate.
    """
    r = _root(root)
    with _writing(r, "curate"):
        con = _connect(r)
        with lake.run(con, "curate") as run_id:
            _curate(con, run_id, gates, rebuild)


def _print_vacuum(report: vac.VacuumReport) -> None:
    b, a = report.before, report.after
    console.print(
        f"vacuum: rewrote {report.rewritten} and merged {report.merged} files, "
        f"expired {report.expired} snapshots, deleted {report.deleted} files"
    )
    console.print(
        f"vacuum: live files {b.live_files:,} -> {a.live_files:,}, "
        f"stats rows {b.stats_rows:,} -> {a.stats_rows:,}"
    )


@app.command()
def vacuum(root: RootOpt = None) -> None:
    """Merge small files, expire snapshots older than the previous curate, delete old Parquet."""
    r = _root(root)
    with _writing(r, "vacuum"):
        con = _connect(r)
        with lake.run(con, "vacuum"):
            _print_vacuum(vac.vacuum(con))


@app.command()
def refresh(
    names: Names = None,
    root: RootOpt = None,
    jobs: Annotated[int, typer.Option("-j", "--jobs")] = 8,
) -> None:
    """Capture, stage, curate, and vacuum in one go. This is what the nightly timer runs."""
    r = _root(root)
    chosen = _select(names)
    with _writing(r, "refresh"):
        con = _connect(r)
        try:
            with lake.run(con, "refresh") as run_id:
                failed = _capture_and_stage(r, con, chosen, jobs)
                _curate(con, run_id, True)
                _print_vacuum(vac.vacuum(con))
                if failed:
                    raise failed
        except UnitsFailed:
            raise typer.Exit(1) from None


def _capture_and_stage(
    r: lake.Root, con: duckdb.DuckDBPyConnection, chosen: list[Dataset], jobs: int
) -> UnitsFailed | None:
    captured = _capture(r, chosen, jobs, None)
    console.print(f"captured {len(captured.fetched)} new units, {captured.skipped} up to date")
    for k, v in captured.failed.items():
        err.print(f"[red]failed[/red] {k}: {v}")
    staged = _stage(r, con, chosen)
    _print_stage(staged)
    if captured.failed or staged.failed:
        return UnitsFailed(captured.failed, staged.failed)
    return None


SETUP_RESUMES = "setup stopped. Rerun nbalake setup to resume, finished work is kept."


@app.command()
def setup(
    names: Names = None,
    root: RootOpt = None,
    jobs: Annotated[int, typer.Option("-j", "--jobs")] = 8,
) -> None:
    """Build the lake on a new machine: check the platform and free disk, refresh, then query it.

    Safe to rerun. Downloads and staged tables are kept, so a rerun resumes where it stopped.
    Unlike refresh, it curates only once every unit is captured and staged.
    """
    r = _root(root)
    found = preflight.problems(
        sys.platform, preflight.free_bytes(r.path), preflight.lake_bytes(r.path), r.path
    )
    for problem in found:
        err.print(f"[red]{problem}[/red]")
    if found:
        raise typer.Exit(2)
    chosen = _select(names)
    with _writing(r, "setup"):
        con = _connect(r)
        try:
            with lake.run(con, "setup") as run_id:
                if failed := _capture_and_stage(r, con, chosen, jobs):
                    raise failed
                _curate(con, run_id, True)
                _print_vacuum(vac.vacuum(con))
        except UnitsFailed:
            err.print(SETUP_RESUMES)
            raise typer.Exit(1) from None
    con = lake.connect(r, read_only=True)
    macros.load(con)
    ((games, first, last),) = con.execute(
        "SELECT count(*), min(season), max(season) FROM nba.games"
    ).fetchall()
    console.print(f"ready: {games:,} games from {first} to {last} in {r.path}")


def _print_snapshot_gaps(records: list[cap.FetchRecord]) -> None:
    if not records:
        return
    through = max(date.fromisoformat(rec.fetched_at[:10]) for rec in records)
    gaps = {
        d.name: cap.missing_dates(d, records, through)
        for d in datasets.ALL
        if d.versions is Versions.ALL
    }
    missing = {name: days for name, days in gaps.items() if days}
    if not missing:
        console.print("snapshots: no missing capture dates")
    for name, days in missing.items():
        console.print(
            f"[yellow]snapshots[/yellow]: {name} has no capture on "
            + ", ".join(str(d) for d in days)
        )


@app.command()
def status(
    root: RootOpt = None,
    datasets_table: Annotated[
        bool, typer.Option("--datasets", help="Also list every dataset's raw and staged counts.")
    ] = False,
) -> None:
    """What the lake is current through, recent runs, snapshot gaps, failing gates, and raw size."""
    r = _root(root)
    records = cap.RawStore(r).records()
    con = lake.connect(r, read_only=True)
    console.print(catalog.currency_line(catalog.currency(con)), markup=False, highlight=False)
    runs = con.execute(
        "SELECT run_id, command, started_at, finished_at, ok, detail FROM lake.meta.runs "
        "ORDER BY started_at DESC LIMIT 5"
    ).fetchall()
    if runs:
        rt = Table("run", "command", "started", "seconds", "ok", "detail")
        for run_id, command, s, f, ok, detail in runs:
            rt.add_row(
                run_id, command, str(s)[:19], f"{(f - s).total_seconds():,.0f}", str(ok), detail
            )
        console.print(rt)
    _print_snapshot_gaps(records)
    gates = con.execute(
        "SELECT gate, violations, checked_at FROM lake.meta.gate_results "
        "QUALIFY row_number() OVER (PARTITION BY gate ORDER BY checked_at DESC) = 1 ORDER BY gate"
    ).fetchall()
    failing = [(g, v, c) for g, v, c in gates if v]
    console.print(f"gates: {len(gates)} checked, {len(failing)} failing")
    if failing:
        gt = Table("gate", "violations", "checked")
        for g, v, c in failing:
            gt.add_row(g, f"{v:,}", str(c)[:19])
        console.print(gt)
    raw_bytes = sum(rec.size for rec in records)
    console.print(f"raw: {len(records)} fetches, {raw_bytes / 1e9:,.2f} GB at {r.raw}")
    if datasets_table:
        staged = {
            name: (units, rows, last)
            for name, units, rows, last in con.execute(
                "SELECT dataset, count(*), sum(rows), max(staged_at) "
                "FROM lake.meta.staged_units GROUP BY 1"
            ).fetchall()
        }
        t = Table("dataset", "raw units", "staged units", "rows", "last staged")
        for d in datasets.ALL:
            raw_n = len(cap.units_in_store(d, records))
            units, rows, last = staged.get(d.name, (0, 0, None))
            t.add_row(d.name, str(raw_n), str(units), f"{rows or 0:,}", str(last or "")[:19])
        console.print(t)


@app.command()
def sql(
    query: Annotated[str, typer.Argument(help="SQL to run against the lake, read only.")],
    root: RootOpt = None,
    limit: Annotated[int, typer.Option(help="Rows to print.")] = 50,
) -> None:
    """Run one query, with the nba macros loaded.

    Tables are nba.*, sdv.*, bref.*, fte.*, l2m.*, shuf.*, odds.*, meta.*.
    """
    con = lake.connect(_root(root), read_only=True)
    macros.load(con)
    cur = con.execute(query)
    names = [d[0] for d in cur.description or ()]
    rows = cur.fetchmany(limit)
    if not rows and names == ["Success"]:
        return
    t = Table(*names)
    for row in rows:
        t.add_row(*(str(v) for v in row))
    console.print(t)


@app.command()
def ui(root: RootOpt = None) -> None:
    """Open the DuckDB UI on the lake, read only. Ctrl-C to stop.

    The nba macros are not loaded here: they are temporary, and the UI runs
    queries on connections of its own. Use nbalake sql or nba sql for them.
    """
    con = lake.connect(_root(root), read_only=True)
    con.execute("INSTALL ui; LOAD ui; CALL start_ui()")
    console.print("DuckDB UI is running. Press Ctrl-C to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


@app.command()
def dictionary(
    root: RootOpt = None,
    out: Annotated[str, typer.Option(help="Markdown file to write.")] = "docs/data-dictionary.md",
) -> None:
    """Write the data dictionary: every table and column, from the registry and the catalog."""
    from nbalake.dictionary import render

    con = lake.connect(_root(root), read_only=True)
    text = render(con)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    console.print(f"wrote {out}")


@app.command("install-skills")
def install_skills(
    dest: Annotated[
        Path | None,
        typer.Option(help="Skills directory. Default: ~/.claude/skills, or the repo's."),
    ] = None,
) -> None:
    """Write the nba-lake, nba-lake-setup, and report skills where Claude Code reads them."""
    runtime = Runtime.current()
    target = dest or skills.default_dest(runtime)
    skills.install(target, runtime, runtime.files / "docs")
    console.print(f"skills written to {target}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
