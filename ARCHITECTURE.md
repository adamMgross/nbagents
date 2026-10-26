# Architecture

Five layers, each reading only the one before it. Capture moves bytes from
mirrors into a content-addressed raw store and records what it fetched. Stage
turns each raw unit into rows of a source-native DuckLake table with lineage
columns. Curate rebuilds the `nba` schema from staged tables in one transaction
that commits only if every quality gate passes, and profiles every table into
`meta.catalog` in the same transaction. Serve is any DuckDB connection
attached read-only to the same catalog, and the `nba` CLI is the one built
for agents: discovery from the catalog, name resolution from an entity index,
domain macros, and a writable scratch database beside the read-only lake. A
declarative registry of 135 datasets is the single source of truth that
capture, stage, the CLIs, the catalog, and the data dictionary are all
generated from.

```
 sources                 capture                raw                      stage                      curate            serve
 -------                 -------                ---                      -----                      ------            -----
 GitHub releases  -+                        blobs/<sha256>           sdv.*      (92 tables)  -+
 GitHub dirs       +-> Index -> units -+--> fetches.jsonl   ------>   shuf.*     (7)           +-> nba.*  ------>  nba (agents)
 GitHub trees      +                   |                              gab.*      (3)           |
 Kaggle           -+   (url, version)  |    (append-only)             fte.*      (5)           |   gates           nbalake sql, ui
                                       |                                                       |   meta.catalog    nbalake.connect()
                       skip if known --+                              l2m.*      (2)          -+   one txn         Python, Polars
                                                                      bref.*     (22)
                                                                      odds.*     (4)
                                                                      meta.*     runs, staged_units, unit_chunks, gate_results, catalog, fingerprints

                       refresh: capture -> stage -> curate -> vacuum (merge, expire before the previous curate, delete old Parquet)
                       registry: datasets/*.py  ->  model.Dataset(fetch, parse, partition, sort, versions)
                       lake: DuckLake catalog.sqlite (WAL) + data/<schema>/<table>/season=YYYY/*.parquet
```

## Modules

- `model.py`: the registry types. `Dataset`, the closed fetch kinds
  `ReleaseAssets | GitDir | GitTree | Kaggle | DropFolder`, the closed parse kinds
  `Parquet | Csv`, and `Versions`. Pure data, no I/O.
- `datasets/`: one module per source declaring its datasets, assembled into
  `ALL`, `BY_NAME`, `SCHEMAS`, and `select()`. Declarations only.
- `lake.py`: `Root` paths, `connect()` (attach DuckLake over SQLite WAL,
  cap memory and spill at 4 GB under `tmp/duckdb`, set the Parquet and file
  size options a lake lacks, create schemas and `meta` tables, `USE lake`),
  `transaction()`, `run()`. Owns every catalog detail.
- `capture.py`: `Index` lists upstream units with version tokens,
  `RawStore` writes blobs and appends the fetch index, `capture()` runs the
  bounded download pool, `units_in_store()` resolves a dataset's units from
  the index alone.
- `stage.py`: `open_source()` dispatches on parse kind to a DuckDB-readable
  source, `load_unit()` creates or reconciles the table and inserts sorted,
  `stage()` replaces changed units one transaction each, recording each
  unit's distinct values of the shipped chunk columns in
  `meta.unit_chunks` in the same transaction (decision 30). A table takes the
  registry's partition and `SORTED BY` order. A changed sort order is set in
  place, and a changed partition fails the dataset until `--rebuild`.
  Given the registry, as the CLI does, `stage()` first drops every staged
  table no registered dataset produces, with its meta rows (decision 37).
- `models/`: one module per curated group declaring `Model(name, kind,
  grain, partition, sort, chunk, description)`, assembled in build order
  into `ALL`. Kinds are `TABLE`, `VIEW`, and `SEED`. A `Chunk(column,
  source)` builds a table one value of the column at a time, the values
  read from the source table. Declarations only.
- `curate.py` and `sql/`: a `Step` pairs a model with its SQL (one file per
  model under `sql/models/`, or generated `read_csv` SQL for a seed under
  `sql/seed/`). A `Gate` is a query under `sql/gates/<group>_*.sql` that
  passes when it returns no rows. `curate()` builds a plan of steps and gates
  in one transaction. Tests pass their own plan. Given the registry, as the
  CLI does, it also drops every `nba.*` table or view no model produces.
- `fingerprint.py`: a model's fingerprint digests its SQL, layout, chunk,
  seed bytes, the `meta.staged_units` rows (unit, sha256, staged_at) of the
  staged tables it reads, and the fingerprints of the curated models it
  reads, found with DuckDB's own parser. A chunked model also has one per
  chunk from the units its rows came from, read from `meta.unit_chunks`. `plan()` is pure and returns
  `Skip`, `Full`, or `Chunks(rebuild, delete)`, and curate matches on it.
- `profile.py`: computes `meta.catalog` (rows, grain, season coverage,
  description per table), `meta.catalog_columns` (type, null rate, range,
  distinct, top values, an example), and `meta.catalog_coverage` (rows per
  season and season type) at the end of curate. A curated table or view
  with a `game_id` takes its season type from `nba.games` (decision 32).
  Any other view's coverage comes from the one staged table it reads.
- `vacuum.py`: rewrites heavily deleted files, merges small ones toward
  128 MB, expires snapshots older than the one the previous curate tagged,
  and deletes scheduled and orphaned Parquet older than an hour (decision
  22). The only code that deletes Parquet.
- `dictionary.py`: renders the data dictionary from the catalog and registry.
- `preflight.py`: checks the platform and free disk before `nbalake setup`
  builds a lake on a new machine.
- `cli.py`: the operator's `nbalake` commands, Rich progress. No logic beyond
  selection, progress, and printing.
- `explore/`: the agent's read-only `nba` CLI (decision 14). `session`
  attaches the lake read only, loads the macros, and attaches scratch.
  `query` runs a statement with a deadline and fetches `limit + 1` rows.
  `render` dispatches on the closed `Format`. `catalog` reads `meta.catalog*`
  and the caveats seed. `entities` resolves names with the pure
  `resolve(candidates, text) -> Match`. `macros` parses `sql/macros/*.sql`
  and each metric's macros (decision 15), ordered by the calls in their
  bodies. `metrics` reads `metrics/<name>/README.md` into a `Metric` with
  its version and macros (decision 34). `script` runs `nba py`. `guide`
  renders the guide and the `nba-lake` skill from `guide.md`, the caveats,
  the macros, and the metrics.
- `metrics/<name>/`: one registered metric, a methodology `README.md` and
  its table macros, computed on demand. `docs/metrics.md` is the workflow.
- `report/`: `nba report` (decision 36). `spec` parses an agent's JSON spec
  into named types and reads the reader-facing `context.toml`. `render`
  runs each block's SQL, then writes one HTML page with the fonts, CSS,
  script, and rows inline. `docs/reports.md` is the workflow, and rendered
  reports live in `reports/`.

## Data flow

Mirrors -> `Index.units()` -> `(url, version)` pairs not in `fetches.jsonl` ->
streamed to a temp file, hashed, renamed to `raw/blobs/` -> one JSON line.

Raw bytes become typed values in `stage.load_unit`: DuckDB's Parquet and CSV
readers for mirror files (with `Dataset.types` casts and `Csv.nulls`). That
is the birthing surface. Typed values become
storage at the `INSERT INTO ... BY NAME ... ORDER BY sort`, where DuckLake
writes partitioned, sorted, zstd Parquet.

Staged tables become curated tables in `curate.build`. A table or seed is
`CREATE OR REPLACE ... LIMIT 0`, `SET PARTITIONED BY`, `INSERT ... ORDER BY`.
A view is created and never scanned. Everything happens inside one
transaction with the gates, so readers see either the previous snapshot or the
whole new one.

## Curated layer

Ten groups build in order, each reading staged tables and earlier groups.
Identity comes first so every fact table joins on NBA Stats ids (decision 7).

```
teams ------+--> games --+--> boxes ------> officiating
            |            +--> odds
players ----+            +--> events
            +--> seasons     tracking
                 |
                 +--> search (after every group)
```

- teams: `franchises` seed (every team code to one `team_id`),
  `team_seasons`, `teams`.
- players: `player_birthplaces` seed (Wikidata), `player_xref` (tiered
  matching across NBA Stats, bref, ESPN,
  FiveThirtyEight), `players`, `unresolved_players`, and `draft_combine`,
  whose prospects keep their NBA Stats id outside `players` (decision 24),
  and `injuries` and `depth_charts` from ESPN's daily snapshots, each with
  a `_latest` view.
- games: `games` from 1946-47, ESPN past the NBA Stats frontier under a
  minted id (decision 28), `game_xref`, `team_elo` (FiveThirtyEight's Elo method
  continued past 2014-15), `arenas` (a Wikidata coordinate seed),
  `team_games` with Elo, rest, and travel,
  `games_cross_source`.
- boxes: `team_box`, `player_box`, `game_inactives`, `box_reconciliation`.
- events: `pbp_actors` (assister, blocker, stealer, and fouled player per
  action, assists and fouls from the v2 copy in `shuf.nbastats`, then
  cdn.nba.com for 2025-26), `pbp_qualifiers` (cdn.nba.com qualifier flags,
  descriptor, foul official, wall clock, 2020-21 to 2025-26), and `pbp`
  (joins both), all tables built by season, and views `possessions`,
  `shots`, `lineup_stints`, `pbp_espn`.
- seasons: `recorded_from` and `us_population` seeds, `player_seasons`,
  `team_season_stats`,
  `raptor`, `player_impact` (sportsdataverse's own RAPM, SPM, BPM, WAR,
  and DARKO-style models), `awards`, and the NBA Stats tables of decision 23:
  `player_season_dash`, `team_season_dash`, `player_season_tracking`,
  `player_season_hustle`, `team_season_hustle`, `player_season_play_types`,
  `matchups_game`, `matchups_season`, and from site_Data
  `player_season_closest_defender` and `team_season_closest_defender`.
- officiating: `game_officials`, `officials`, `l2m_calls`, `l2m_games`.
- odds: `odds_teams` seed, `game_lines` (decision 13).
- search: `caveats`, `player_aliases`, and `team_aliases` seeds, and
  `entity_index`: every player, franchise name, and game with a normalized
  key, aliases, seasons, and context for `nba find`.

Disagreement between sources is published, not hidden: report tables
(`games_cross_source`, `box_reconciliation`, `unresolved_players`) list every
mismatch, and gates bound the rate with the threshold in the gate's name.

## External systems

| System | Purpose | Auth | Verified | License |
|---|---|---|---|---|
| api.github.com releases and contents | list units and change tokens | optional `GITHUB_TOKEN` | 2026-10-21 | n/a |
| github.com release assets (sportsdataverse-data) | 43 NBA datasets as per-season Parquet | none | 2026-10-21 | not verified |
| raw.githubusercontent.com shufinskiy/nba_data | 7 play-by-play archives | none | 2026-10-21 | not verified |
| api.github.com git trees and raw.githubusercontent.com gabriel1200/site_Data | shooting by closest defender, 324 CSVs | optional `GITHUB_TOKEN` | 2026-10-25 | not verified |
| raw.githubusercontent.com fivethirtyeight/data | Elo and RAPTOR | none | 2026-10-21 | CC BY 4.0 |
| raw.githubusercontent.com atlhawksfanatic/L2M | Last Two Minute reports | none | 2026-10-21 | not verified |
| kaggle.com api v1 (sumitrodatta) | Basketball-Reference season tables | none | 2026-10-21 | CC0 |
| query.wikidata.org | arena coordinates and player birth countries, fetched once into the `arenas` and `player_birthplaces` seeds, not at refresh | none | 2026-10-24 | CC0 |
| fred.stlouisfed.org series POP | US population per year, fetched once into the `us_population` seed | none | 2026-10-24 | public domain (Census Bureau) |

## Storage

Under `Root` (`$NBALAKE_ROOT`, default `~/.local/share/nbalake`):

| Path | What | Rule |
|---|---|---|
| `raw/blobs/ab/<sha256>` | exact upstream bytes | write once, never rewritten |
| `raw/fetches.jsonl` | one line per fetch | append-only |
| `catalog.sqlite` | DuckLake metadata, WAL mode | owned by DuckLake |
| `data/<schema>/<table>/[season=YYYY/]*.parquet` | table data | owned by DuckLake, immutable files |
| `scratch.duckdb` | the agent's tables from `nba sql --out` and `nba py` (decision 16) | the agent's to drop |
| `tmp/` | in-flight downloads, extracted archives, DuckDB spill for every session under `tmp/duckdb` | disposable |

Raw is the only irreplaceable layer and the only one to back up.

## Build, run, deploy

`uv sync` creates the environment. `nbalake refresh` is the whole pipeline.
`nbalake setup` is the first build on a new machine: preflight, then
refresh that curates only once every unit is in, then one query. The
`nba-lake-setup` skill drives it for an agent.
Every write command holds `<root>/writer.lock`, so a second writer exits 75
instead of running beside it. Tests run offline against a temp lake and a
fake upstream over `httpx.MockTransport`.

`packaging/build.py` freezes both commands into one PyInstaller app with
the DuckDB extensions and the skill docs inside, so it runs with no Python
and no extension download. `Runtime` (`REPO` or `APP`) is the one place that
knows which it is running as: command prefixes, the extension directory,
and where the docs live. `nbalake install-skills` renders the skills for
that runtime from the templates beside `guide.md`.

## Shape

- Network I/O happens only in `capture.py`, except that `lake.connect` and
  `cli.ui` run `INSTALL` for the ducklake, sqlite, and ui extensions, which
  downloads them once per machine. File I/O happens in `capture.py` (blobs,
  index), `stage.py` (archive extraction to `tmp`), and `lake.py`
  (catalog). `model.py` and `datasets/` are pure data.
- `Fetch`, `Parse`, and `Versions` are closed and dispatched
  with `match` statements that list every variant. A fallback branch is a bug.
- A dataset's units are resolved from `raw/fetches.jsonl` by url prefix and
  key pattern. Stage never consults the network or the registry's upstream
  listing.
- Every staged row carries `_unit`, `_sha256`, `_fetched_at`. Every staged
  unit has one row in `meta.staged_units`.
- Peak memory is one unit: DuckDB streams Parquet and CSV units.
- The hot path is DuckDB's own insert and scan. Python never touches
  individual staged rows.
- Only the five play-by-play tables over 256 MB that are replaced a season
  at a time are season partitioned (decision 21). Every other table sorts
  with `season` first and is merged toward 128 MB files, so the catalog
  holds few files and a season filter prunes row groups. A season-and-key
  filter on a partitioned table and a season filter on each event view read
  one file, pinned by counted-work tests on `Total Files Read`.
- `raw/fetches.jsonl` and `raw/blobs/` are append-only. `meta.runs` and
  `meta.gate_results` are append-only, one insert per command or curate.
  A curated table is rebuilt whole, or one chunk at a time by deleting and
  reinserting the chunk, and never patched by hand. Curate rebuilds only
  what its fingerprint says changed, `--rebuild` everything.
- Time travel reaches back to the snapshot the previous curate published
  and no further. Vacuum deletes a file only an hour after it was scheduled,
  so a reader mid-query keeps its files, pinned by a test.
- A view only renames, casts, filters, or joins small dimension tables, and
  any window, `QUALIFY`, or event join is a table built by chunk (decision
  18), pinned by a test over the shipped SQL. Peak memory in curate is one
  chunk, and a nightly curate rebuilds only the chunks whose units changed.
- The `nba` process attaches the lake read only and never writes it.
  Scratch is the one writable database. `nba tables` and `nba describe`
  read only `meta.*` and the packaged caveats, pinned by a test that moves
  every other data file away first.
- `nba sql` streams and fetches `limit + 1` rows, pinned by a test that a
  10^12-row result returns inside a five second deadline.
- Everything an agent reads is generated: the skill and `nba guide` from
  `guide.md`, the caveats seed, and the macro headers, pinned equal by a
  test. Catalog facts come from the data at curate.
- Curate tests build any subset of the shipped plan against empty tables
  created from `tests/fixtures/staged_schema.json`, a snapshot of the real
  staged schemas, so a renamed upstream column fails a test.
