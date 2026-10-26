# NBA lake

A local DuckDB lake of every free NBA dataset: 80,000 games from 1946-47,
box scores, play-by-play, shots, lineups, season tracking from 2013-14,
awards, Elo, RAPTOR, betting lines, and Last Two Minute reports. One id
model across sources. Query it with `nba`, which is read only.

## Workflow

1. Before any analysis beyond a lookup, read `docs/basketball/README.md`,
   the basketball primer, and the pages it names for the question: how
   possessions, shot value, roles, schemes, eras, and noise shape every
   number. Run its checklist before reporting a number.
2. `nba tables` to see the curated `nba.*` tables, `nba search <word>` when
   you do not know which table holds a stat, and `nba describe <table>`
   before writing SQL against one. Read its caveats. Before concluding data
   is missing, ask `nba coverage`, which says what exists from when.
3. `nba find player|team|game <text>` to turn a name into an id. Never guess
   an id and never filter on a name column.
4. `nba sql "<query>"` to answer, from a macro when one fits.
<!-- repo -->
5. For several steps, keep each intermediate with `--out <name>` and build
   on `scratch.<name>`, or write one `nba py` script. Never rerun an
   upstream query to get rows you already computed.
<!-- end -->
<!-- app -->
5. For several steps, keep each intermediate with `--out <name>` and build
   on `scratch.<name>`. Never rerun an upstream query to get rows you
   already computed.
<!-- end -->
6. When the person asks for an analysis to look at or share, not a quick
   lookup, finish with a report: write `reports/<date>-<slug>.json` and run
   `nba report` on it. See Reports.

## Commands

| Command | Example |
|---|---|
| `nba guide` | this text |
| `nba tables [pattern]` | `nba tables shot` or `nba tables 'sdv.*'` |
| `nba describe <table>` | `nba describe nba.player_box`, `--columns` for the column list only |
| `nba search <word>` | `nba search rebound` |
| `nba coverage <table or words>` | `nba coverage 'playoff minutes'`: from which season, per season type |
| `nba find player <name>` | `nba find player steph` |
| `nba find team <name>` | `nba find team sonics` |
| `nba find game <words>` | `nba find game 'finals 2016 game 7'` |
| `nba sql "<query>"` | `nba sql "from nba.games where season = 2016 limit 5"` |
| `nba sql "<query>" --explain` | files read, rows per table, and the plan, no rows |
| `nba macros` | the domain macros with examples |
| `nba metrics [name]` | `nba metrics career_postseason`: the methodology |
<!-- repo -->
| `nba py <file or ->` | `nba py - <<'EOF'` with `con`, `pl`, `duckdb` |
<!-- end -->
| `nba report <spec.json>` | `nba report reports/2026-10-24-best-seasons-since-1974.json` |

Every command has `--help` with options and examples.

## Macros

Table macros encode the joins and caveats for common questions. Use them
before writing the join by hand: `nba sql "from on_off(201939, 2016)"`.
`nba macros` prints each with an example. NULL for `season_type` means
every type.

<!-- macros -->

## Metrics

A metric is a settled, versioned definition of something the lake does not
record, computed on demand by its macros. `nba metrics <name>` prints the
methodology, including its limits. Read it before reporting a number, and
quote the version with it: "career_postseason v1". To build a new one, follow
`docs/metrics.md`.

<!-- metrics -->

## Reports

A report is one HTML file a person opens in a browser or shares: a
finding, up to four tiles, blocks from SQL (sortable tables, bar, line,
scatter, and small multiple charts, and text), and a collapsed account of
why, how, and from what data, written for a reader who knows nothing about
the lake. The `report` skill, `/report <question>`, walks the whole job,
and publishes the page as a Claude artifact too, so it opens in the app. You write a JSON spec, and `nba report` runs
its queries and renders the page in the house design. `docs/reports.md` has
the spec. Background on datasets, metrics, and stats comes from context
keys, so write only what is particular to this analysis. Each query returns
at most 2,000 rows. Tell the person the path of the HTML file.

## Conventions

- `season` is the end year: 2016 means 2015-16. The current season is 2027.
- Keys: `game_id` (VARCHAR, NBA Stats ids like `0041500407` from 1996-97,
  FiveThirtyEight ids before, and `espn` plus the ESPN id for recent games
  NBA Stats has not published yet, which `nba.game_xref` maps once it
  does), `team_id` (one per franchise across moves and
  renames), `player_id` (NBA Stats person id, or 9000000000000 and up for
  players NBA Stats never listed).
- Filter play-by-play, possessions, and shots by `season` as well as
  `game_id`: `where season = 2016 and game_id = '0041500407'`. A `game_id`
  alone reads most seasons' files.
- `nba.game_inactives` lists who sat out each game from 1996-97, for
  with-and-without questions: `select i.player_id is not null as out,
  count(*), avg(won::int) from nba.team_games t left join
  nba.game_inactives i on i.game_id = t.game_id and i.player_id = 201939
  where t.team_id = 1610612744 and t.season = 2016 and t.season_type =
  'regular' group by 1`. `nba.game_officials` names each game's referees.
- `season_type` in curated tables is one of regular, playoffs, play-in,
  preseason, all-star, nba-cup. Filter it explicitly. `nba.team_games`
  includes preseason. Staged tables keep the source's spelling, like
  `Regular Season`, so check a staged column's values before filtering.
- Playoff rounds and brackets: `nba.playoff_series`, one row per series
  with `round`, `best_of`, home court, wins, `game_ids`, Elo entering the
  series, `home_court_series_prob`, and `next_series_id`. Do not rebuild
  series from games. `elo_game_prob` and `elo_series_prob` price a
  hypothetical game or series.
- Who is injured now: `from nba.injuries_latest`. Depth charts:
  `nba.depth_charts_latest`. Both keep every daily snapshot in
  `nba.injuries` and `nba.depth_charts` by `snapshot_date`.
- `nba.teams` holds each franchise's current name. `nba.games` and
  `nba.team_games` already carry the names teams used that season
  (`home_team_name`, `team_name`, `opponent_name`), so a 1949 Lakers game
  reads Minneapolis. For a code, join `nba.team_seasons` on `team_id` and
  `season`.
- A traded player has one `nba.player_seasons` row per team plus a total
  row with `multi_team` true. `leaders` picks the total for you.
- Minutes are stored as `seconds`.
- Curated tables are `nba.*`. Staged source tables (`sdv.*`, `bref.*`,
  `fte.*`, `shuf.*`, `l2m.*`, `odds.*`) hold every source
  column and are there when a curated table lacks a field.
- DuckDB SQL: `from t` without `select *`, `qualify`, `filter`, `list`,
  `struct`, `arg_max`, `exclude`. Lambdas are `lambda x: x + 1`, not
  `x -> x + 1`. No Postgres-only syntax.

## Output

- Data on stdout, notices on stderr. Exit 0 ok, 1 query or lookup error,
  2 bad usage.
- After the rows, `nba sql` prints on stderr every caveat of the tables the
  query reads, macros included, that concerns the whole table or a column
  the query or its result names: `caveat nba.team_games.elo_pre (2016 on):
  ...`. Read each one before answering. Past four, a line names the `nba
  describe` that lists the rest.
- `--format md` (default), `jsonl`, `csv`, or `table`. `--limit` defaults to
  50 rows and a notice says when more exist. Floats print with three
  decimals and long cells are cut at 80 characters. `--raw` turns both off.
- `--out <name>` writes every row to `scratch.<name>` and prints the row
  count instead of rows. Scratch is a DuckDB file that persists between
  sessions, so name tables for the task (`curry_2016_games`, not `t1`),
  list them with `nba tables scratch.`, and drop what you no longer need:
  `nba sql "drop table scratch.<name>"`. Each `--out` keeps the SQL that
  made the table, which `nba describe scratch.<name>` prints, so a later
  session can tell how it was built.
- A macro you make for the task lives in scratch and persists too:
  `nba sql "create or replace macro scratch.per_game(x, g) as x / g"`.
  Always call it qualified, `scratch.per_game(pts, g)`, since an unqualified
  name does not reach scratch. `nba macros` lists yours under yours.
<!-- repo -->
  A macro worth keeping for every session moves to
  `src/nbalake/sql/macros/<name>.sql` with the description and example
  header lines and a test in `tests/test_macros.py`, after which
  `nba macros` lists it for everyone.
- `nba py` scripts get `con` (lake read only, macros, scratch writable),
  `pl` (polars), and `duckdb`. `con.sql("...").pl()` returns a polars
  frame. Print summaries: output past 20,000 characters is cut. Scripts
  stop after 300 seconds (`--timeout`). Beside DuckDB's 4 GB, a script's
  own frames and objects get 4 GB more. A DuckDB result or Python object
  past it stops the script with the cap error. Polars' own operations past
  it end the process with `memory allocation of N bytes failed`, which
  means the same: aggregate in SQL first and pull the summary into polars.
<!-- end -->
- Queries stop after 60 seconds (`--timeout`). A session has 4 GB of
  memory and 4 GB of disk spill, and a query past either stops with an
  error. Narrow it to a season, game, or player, or use a macro, before
  anything else. Before `--out` on a large query or a longer `--timeout`,
  run it with `--explain`: the Parquet files it reads are its cost, and a
  `season` filter on play-by-play reads one file where a bare `game_id`
  reads one per season.
<!-- repo -->
  `--allow-spill SIZE` on `nba sql` and `nba py` raises the spill cap for
  one run.
<!-- end -->
<!-- app -->
  `--allow-spill SIZE` on `nba sql` raises the spill cap for one run.
<!-- end -->
  Ask the owner first and name the size, and never pass it without their
  yes.

## Caveats

These cause most wrong answers. `nba describe` repeats them per table.

<!-- caveats -->

## More

`docs/dataset-guide.md` explains every source and table, and
`docs/data-dictionary.md` lists every column.
