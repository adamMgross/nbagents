# NBA Lake

A local NBA data lake: every free dataset, one identity model, one query
surface, kept current by a nightly timer. The rule that matters most: raw is
append-only and content addressed, and everything downstream is rebuilt from
it. Never hand-edit a table.

Using the lake rather than developing it, on a machine of your own? The
`nba-lake-setup` skill builds it and the `nba-lake` skill answers questions.
Skip everything below, and never commit or push.

This repo follows `~/.claude/CLAUDE.md` in full. This file adds only what is
specific to this repo and not derivable from the code.

## Reading order

- `ARCHITECTURE.md`: layers, modules, storage, and the Shape the code holds to.
- `docs/metrics.md`: how to build and register a metric, like
  `career_postseason`.
- `docs/reports.md`: the report spec `nba report` renders to one HTML page.
- `docs/basketball/README.md`: the basketball primer every analysis
  reads first, with topic pages on analysis, stats, offense, defense,
  and history.

## Commands

```bash
uv sync                                   # once, Python 3.13
export GITHUB_TOKEN=$(gh auth token)      # optional, lifts the GitHub API limit
uv run nbalake datasets                   # the registry, with raw unit counts
uv run nbalake capture [names...]         # download new upstream versions into raw
uv run nbalake stage [names...]           # load raw units into <source>.<table>
uv run nbalake curate                     # rebuild changed nba.* models, gated, one transaction
uv run nbalake vacuum                     # merge small files, expire old snapshots
uv run nbalake refresh                    # capture, stage, curate, vacuum: the nightly job
uv run nbalake setup                      # first build on a new machine: preflight, refresh, query
uv run nbalake status                     # per dataset state, runs, gate results
uv run nbalake sql "select ..."           # one query, read only
uv run nbalake ui                         # DuckDB UI on the lake, read only
uv run nbalake dictionary                 # regenerate docs/data-dictionary.md
uv run nba guide                          # the agent CLI, read only: guide, tables,
                                          #   describe, search, find, sql, py, macros,
                                          #   metrics
uv run nba report reports/<date>-<slug>.json        # render a report spec to HTML
uv run nbalake install-skills             # regenerate .claude/skills after changing
                                          #   guide.md, setup.md, report.md, caveats.csv,
                                          #   a macro header, or a metric
uv run pytest                             # the suite, offline, in parallel, under a minute
uv run pytest -n 0 tests/test_x.py -k y   # one test, serially, without worker startup
uv run ruff check src tests && uv run ruff format --check src tests
```

Names accept a dataset (`sdv.nba_stats_pbp`), a schema (`bref`), or a glob
(`sdv.leaguedash_*`). The lake lives at `$NBALAKE_ROOT`, default
`~/.local/share/nbalake`.

From Python: `con = nbalake.connect(nbalake.Root.resolve(), read_only=True)`
returns a DuckDB connection with the lake attached and `USE lake` applied, so
`con.sql("select * from nba.games").pl()` works.


## Invariants

Breaking one of these is a defect, not a tradeoff.

- **Raw is append-only.** A blob is never rewritten and `raw/fetches.jsonl`
  is never edited. A new upstream version is a new line and a new blob.
- **Stage never touches the network and curate never touches raw.** Each
  layer reads only the layer before it.
- **Curated tables are rebuilt, never patched.** A fix goes in the SQL model
  or the registry, then `nbalake curate`.
- **A failed gate publishes nothing.** Curate runs in one DuckLake transaction
  and `GateFailure` rolls it back. Gate results are recorded either way.
- **Season is the end year.** 2026 means 2025-26 in every table. Sources that
  name files by start year (shufinskiy) are converted at stage.
- **Schema drift never narrows.** Columns are added and numeric types widened.
  Anything else raises `SchemaDrift` and the unit rolls back.
- **Every performance claim has a counted-work test.** Files read from
  `EXPLAIN ANALYZE`, row group sizes from `parquet_metadata`. No timing asserts.

## Curated models

- Validate model SQL against real data without writing to the lake: create a
  scratch DuckLake whose staged schemas are views over the real lake attached
  read only, then run `curate(con, steps=..., gates=..., enforce_gates=False)`.
- The lake is for analysis across seasons. A source covering one season
  does not belong. Retire a dataset or model by deleting its declaration:
  the next `nbalake stage` and `nbalake curate` drop its tables.
- `nba describe` and `nba tables` read `meta.catalog`, which only `curate`
  writes. After adding a model or staging a new dataset, run `nbalake
  curate` before expecting `nba` to list it.
- Curate skips a model whose fingerprint matches the published one. A
  change to curate's own code, not the model SQL, needs `nbalake curate
  --rebuild`. A test that writes a staged table directly must also write
  its `meta.staged_units` row, as stage does, or pass `rebuild=True`.
- Curate tests use `tests/curated.py`: `empty_lake(root, sources(*models,
  gate_prefix=...))`, `insert`, `build_models`, `gate`. After a stage that
  changes schemas, refresh the snapshot with
  `uv run python tests/fixtures/snapshot_staged_schema.py`.
- A gate with a threshold names it (`..._under_0_1_percent`).

## Not yet

The owner does not want CI yet. Do not add a CI workflow. The nightly
timer is installed (decision 27).

## Traps

- DuckDB 2.0 Python raises `ResourceInUseException` if `con.sql()` follows an
  `execute()` whose result was not consumed. Internal code uses `execute()`
  and fetches. `lake.connect` leaves no pending result for callers.
- A DuckLake catalog on a DuckDB file is single-process. The lake uses
  `ducklake:sqlite:` in WAL mode so a reader can attach during a write. Do not
  change the catalog kind without rereading decision 2.
- Fetching `TIMESTAMP WITH TIME ZONE` through `fetchall()` needs `pytz`,
  which is a dependency for that reason only.
- sportsdataverse already publishes `_2027` files for the 2026-27 season, so
  the current season is 2027, not 2026.
- The 22 `bref.*` datasets share one Kaggle zip. Capture fetches it once and
  each dataset extracts its member.
- R-generated CSVs (Kaggle, L2M) spell null as `NA`. Those datasets declare
  `Csv(nulls=("", "NA"))`.
- Unauthenticated GitHub API calls are capped at 60 per hour. A capture of
  every dataset uses about 10. Set `GITHUB_TOKEN` when iterating.
- The ehallmar odds files hold NBA Stats game ids with leading zeros, so they
  stage as all-VARCHAR. Stage `types` cast after inference and would drop the
  zeros.
- ESPN play-by-play spreads before 2012-13 are a filler 2.5 with
  `game_spread_available` false. `nba.game_lines` keeps only available ones.
- Use `fetchall()`, not `fetchone()`, so no `execute()` result stays pending.
- `pa.Table.from_pylist` takes its columns from the first row only. The test
  `insert` helper unions keys for that reason.
- In DuckDB, `QUALIFY` runs before `DISTINCT`. Deduplicate in a subquery
  before counting candidates.
- A cast inside an aggregate runs before its `FILTER` clause. Cast inside a
  `CASE` instead.
- A table staged before the null-type fix can still carry a `"NULL"` column.
  `nbalake stage --rebuild <dataset>` fixes it.
- DuckDB macro parameters collide with same-named columns once a query
  joins two tables that have them. Each macro copies its parameters into a
  one-row `args` CTE and references `a.<param>` only.
- DuckLake answers `count(*)`, `min`, and `max` from file statistics, so a
  test that must prove data files are read uses a filter.
- DuckDB 2.0 rejects the `x -> x` lambda arrow. Write `lambda x: x`.
- DuckDB checks a table macro's tables when the macro is created unless a
  parameter binds first, and test lakes lack most tables. Read `args`
  before any table: `FROM args a JOIN nba.x ...`.
- Every `lake.connect` session, stage and curate included, caps memory
  and spill at 4 GB and spills under the lake's `tmp/duckdb`. An owner
  session that needs more sets `memory_limit` or `max_temp_directory_size`
  itself after connecting.
- Every write command holds `<root>/writer.lock` and exits 75 while
  another holds it, including the nightly run from 07:30 or from boot.
  Check `systemctl --user status nbalake-refresh` before a long manual
  curate.
- `pkill -f` with a pattern in your own command line kills your shell. Use
  `pgrep -f "[p]attern"`.
- A view that casts `season` (`season::INTEGER`) or computes a window not
  partitioned by `season` reads every season file for a one-season filter.
  The event views keep the staged type, and `nba.pbp` partitions its
  window by season.
- A dataset whose registry partition changes fails at stage with
  `LayoutDrift` until `nbalake stage --rebuild <dataset>`, because files
  written under an old partition never merge. A changed sort order needs
  nothing, stage sets it and vacuum's merges apply it.
- `count(column)` is also answered from statistics, even through a view.
  A counted-work test selects `*`.
- Every filtered query on the lake costs about 0.45 microseconds per row of
  the catalog's `ducklake_file_column_stats` per filtered column, and that
  table holds a row per column of every file of every table. Many small
  files anywhere slow every query. SQLite indexes do not help.
