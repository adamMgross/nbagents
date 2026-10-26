---
name: nba-lake
description: Answer questions about NBA and BAA games, players, teams, box scores, play-by-play, shots, lineups, tracking, awards, betting lines, and Last Two Minute reports from the local NBA lake with the read-only nba CLI. Use for any basketball stats question, lookup, comparison, or analysis.
---

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
5. For several steps, keep each intermediate with `--out <name>` and build
   on `scratch.<name>`, or write one `nba py` script. Never rerun an
   upstream query to get rows you already computed.
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
| `nba py <file or ->` | `nba py - <<'EOF'` with `con`, `pl`, `duckdb` |
| `nba report <spec.json>` | `nba report reports/2026-10-24-best-seasons-since-1974.json` |

Every command has `--help` with options and examples.

## Macros

Table macros encode the joins and caveats for common questions. Use them
before writing the join by hand: `nba sql "from on_off(201939, 2016)"`.
`nba macros` prints each with an example. NULL for `season_type` means
every type.

- `elo_game_prob(elo_home, elo_away, home_edge := 100)`: The Elo chance the home team wins one game. nba.team_games.elo_win_prob uses home_edge 100, and 0 at a neutral site.
- `leaders(stat, season, min_games := 58, per_game := false, lg := NULL)`: The top players on one nba.player_seasons column, one row per player with traded players' season totals, over min_games. per_game divides by games. lg NULL means NBA and BAA, not ABA.
- `per_100(points, possessions)`: A rate per 100 possessions, NULL when possessions is zero.
- `player_games(player_id, season := NULL, season_type := 'regular', include_dnp := false)`: A player's game log with date, team, opponent, home, result, score, minutes, box line, and the median closing spread for his team. Games he did not play are left out unless include_dnp. season and season_type NULL mean all.
- `shot_zones(player_id, season, season_type := 'regular')`: A player's shots by zone with attempts, makes, percentage, share of his attempts, and the league percentage and share for the same zone and season.
- `team_games_of(team_id, season, season_type := 'regular')`: One team's games in a season with opponent, result, rest, Elo (FiveThirtyEight's through 2014-15, the lake's own after), the median closing spread, and the result against it. season_type NULL means every type, including preseason.
- `against_the_spread(team_id, season, season_type := 'regular')`: A team's record against the median closing spread in a season, split by home or away and favorite or underdog, with every subtotal. Lines exist from 2006-07.
- `elo_series_prob(elo_home_court, elo_other, best_of := 7, home_edge := 100)`: The Elo chance the team with home court wins a best_of series, hosting (best_of + 1) / 2 of the games, as nba.playoff_series.home_court_series_prob.
- `lineups(team_id, season, min_possessions := 100, season_type := 'regular')`: Five-man units for one team, or every team when team_id is NULL, with possessions and ratings per 100. A unit needs min_possessions on offense and again on defense.
- `on_off(player_id, season, season_type := 'regular')`: Team points for and against per 100 possessions with the player on and off the floor, per team he played for, over the games he played. On/off is the on row's net_rating minus the off row's. Possession points run low before 2017-18.

## Metrics

A metric is a settled, versioned definition of something the lake does not
record, computed on demand by its macros. `nba metrics <name>` prints the
methodology, including its limits. Read it before reporting a number, and
quote the version with it: "career_postseason v1". To build a new one, follow
`docs/metrics.md`.

- `career_postseason` (version 2): Career postseason achievement from 1984, as playoff wins above what the season's weakest playoff team would have won against the same opponents, weighted by round and split by each player's share, which from 1994 reflects how he played that postseason. `postseason_team_credit`, `postseason_game_credit`, `postseason_season_credit`, `career_postseason`
- `career_postseason_basic` (version 1): Career postseason achievement from 1958, the career_postseason team credit with rounds counted back from the Finals, split by regular-season win shares so every era is measured the same way. `postseason_basic_season_credit`, `career_postseason_basic`
- `era_wins` (version 1): Wins above replacement per player season from 1974, in its own league and translated into the 2025-26 league by league strength, the free throw whistle, and wins per point, so seasons compare across eras. `league_strength`, `whistle_trips`, `wins_per_point`, `free_throw_environment`, `era_wins_season`, `career_era_wins`
- `quality_wins` (version 1): Regular-season wins weighted by how hard each one was, against the opponent's strength at the time and the venue, for every team from 1947 and split among the players who played each game. `quality_win_team_game`, `quality_win_game`, `quality_win_team_season`, `quality_win_season`, `career_quality_wins`

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
- Queries stop after 60 seconds (`--timeout`). A session has 4 GB of
  memory and 4 GB of disk spill, and a query past either stops with an
  error. Narrow it to a season, game, or player, or use a macro, before
  anything else. Before `--out` on a large query or a longer `--timeout`,
  run it with `--explain`: the Parquet files it reads are its cost, and a
  `season` filter on play-by-play reads one file where a bare `game_id`
  reads one per season.
  `--allow-spill SIZE` on `nba sql` and `nba py` raises the spill cap for
  one run.
  Ask the owner first and name the size, and never pass it without their
  yes.

## Caveats

These cause most wrong answers. `nba describe` repeats them per table.

- `nba.team_games.elo_pre` (2016 on): FiveThirtyEight Elo through 2014-15, the lake's own Elo from 2015-16 (elo_source), computed with FiveThirtyEight's method from their 2013-14 closing ratings. It reproduces their 2014-15 within 2 points. Its fixed 100-point home edge predicts home teams win 62 percent, and they won 55 to 59 percent from 2015-16, so elo_win_prob is overconfident: teams given 86 percent won 81. elo_fit_* from 2014-15 fits the home edge to the previous three seasons and is calibrated within one point. Preseason and all-star games carry none.
- `nba.games.neutral_site` (2020): True for the 172 games of the 2020 Orlando bubble, which ESPN marks as home games.
- `nba.team_games.season_type` (all): Holds preseason, all-star, play-in, and nba-cup games beside regular and playoffs. Filter season_type.
- `nba.games.season_type` (all): nba-cup is only the NBA Cup final, which does not count in the standings. Every other Cup game is regular.
- `nba.player_box.started` (1997-2017): NULL on NBA Stats rows from 1996-97 through 2000-01, and from 2001-02 to 2016-17 where ESPN's game roster does not list five starters for the team, about 1.4 percent of team games. started_source says whether NBA Stats or ESPN set it. ESPN rows for 1993-94 to 1995-96 carry it.
- `nba.player_box.played` (all): Rows for players who did not play carry 0 in every stat on NBA Stats rows, not NULL. Filter played before averaging or counting games.
- `nba.player_box.player_id` (1994-1996): About 2,100 ESPN rows have no player_id because the ESPN name did not resolve. Team totals still include them.
- `nba.player_seasons.multi_team` (all): A traded player has a row per team plus a total row with multi_team true and no team_id. Use the total row for a season figure, never both.
- `nba.raptor.model` (all): Each season has a modern and a historical RAPTOR row per player. Filter model before averaging.
- `nba.possessions.points` (1997-2017): Points run about 1.5 per team-game under the box score before 2017-18. Rates from possessions read low in those seasons.
- `nba.shots.x_feet` (all): About 9,900 of 6.3M shots have coordinates outside the court, including heaves and bad source rows. Bound x_feet and y_feet for charts.
- `nba.shots.season_type_id` (all): No season_type column. season_type_id 2 is regular, 4 playoffs, 5 play-in, 6 nba-cup. Join nba.games for the name.
- `nba.game_lines.home_spread` (all): Negative means the home team is favored. Lines start in 2006-07 and several books can quote one game, so pick a source and book or take the median.
- `sdv.espn_nba_pbp.game_spread` (before 2013): A filler 2.5 with game_spread_available false before 2012-13. Use nba.game_lines.
- `sdv.leaguedash_player_tracking_pullupshot` (before 2014): Rows exist from 1996-97 but every tracking value before 2013-14 is zero. Only games, wins, losses, and minutes are real.
- `sdv.leaguedash_player_tracking_catchshoot` (before 2014): Rows exist from 1996-97 but every tracking value before 2013-14 is zero. Only games, wins, losses, and minutes are real.
- `nba.l2m_calls` (2015 on): Last Two Minute reports grade only the final two minutes of games within three points, plus overtime, from 2014-15.
- `nba.pbp.action_type` (all): Each block and steal is also its own row with an empty action_type and the action_number of the miss or turnover. Count block_player_id and steal_player_id, which sit on the primary row only.
- `nba.pbp.fouled_player_id` (before 2006): NULL before 2005-06. The source did not record who was fouled.
- `nba.pbp.assist_player_id` (2027 on): NULL from 2026-27 on and in preseason, all-star, play-in, and nba-cup games, which neither the v2 source nor cdn.nba.com covers. 2025-26 comes from cdn.nba.com. fouled_player_id is NULL there too. Blocks and steals are complete.
- `nba.pbp.qualifiers` (2021 to 2026): qualifiers, fast_break, second_chance, from_turnover, points_in_paint, descriptor, official_id, and wall_clock come from cdn.nba.com and are NULL outside 2020-21 to 2025-26 regular seasons and playoffs, and on block and steal rows.
- `sdv.leaguedash_player_stats_base.team_id` (all): One row per player season on the player's last team, so a traded player's whole season sits under that team. Curated season tables name it last_team_id.
- `nba.player_season_dash.last_team_id` (all): The team the player ended the season with. A traded player has one row for his whole season under it, and team_count says how many teams he played for. Use nba.player_box for games by team.
- `nba.player_season_tracking.last_team_id` (all): The team the player ended the season with. A traded player has one row for his whole season under it.
- `nba.player_season_hustle.last_team_id` (all): The team the player ended the season with. A traded player has one row for his whole season under it.
- `nba.player_season_closest_defender.last_team_id` (all): The team the player ended the season with. A traded player has one row per band for his whole season under it.
- `nba.player_season_closest_defender.games_with_shot` (all): Games with at least one attempt in that band, not games played. gp is games played.
- `nba.player_season_closest_defender.fga` (all): Attempts with no tracked defender fall in no band, so the four bands can sum to a little under the season's fga.
- `nba.player_impact.rapm` (all): sportsdataverse's single-season ridge RAPM from stats.nba.com play-by-play and rotations, built by hoopR-nba-stats-data. o_rapm and d_rapm split it. The playoff rows rest on about 15 games a team.
- `nba.player_impact.adj_rapm` (all): RAPM with a prior: the previous season's possession-weighted regular season and playoff SPM, and for playoffs that season's regular season SPM. The first season of each sportsdataverse run has no prior.
- `nba.player_impact.spm` (all): A box-score SPM fitted to RAPM once per regular season and reused for playoffs, so playoff values are on the same scale but directional.
- `nba.player_impact.bpm` (all): sportsdataverse's reimplementation of BPM 2.0 from box logs and listed positions. It will not match Basketball-Reference's published BPM exactly.
- `nba.player_impact.war` (all): WAR on the RAPM rating with points per win fitted each regular season from team game logs and a replacement level of -2.0 per 100.
- `nba.player_impact.darko_projected_rating` (all): sportsdataverse's Kalman forecast in the style of DARKO, not the published DARKO. It projects the NEXT season, both season types carry the same value, and it is NULL until its panel spans two seasons.
- `nba.player_impact.primary_team_id` (all): The team the player played the most games for that season. teams lists every team, most games first.
- `nba.team_games.travel_km` (all): Great-circle kilometers from the previous competitive game of the season. A game is placed at the ESPN venue for neutral sites, else at the home team's season arena as Basketball-Reference lists it, so a team that split a season between arenas is placed at the listed one. NULL for the first game of a season and where the arena is unknown: Seattle 1978-79 to 1984-85, Golden Hall and Tulane Gym in the ABA, and neutral sites before 1993-94.
- `nba.games.game_id` (current): A completed game newer than every NBA Stats game has source espn and game_id 'espn' plus its ESPN id. When NBA Stats publishes the game the row takes the NBA Stats id, and nba.game_xref maps the old id (source minted) to it. Its boxes come from ESPN and carry no plus_minus or team minutes, and play-by-play is in pbp_espn only.
- `nba.injuries` (2027 on): One row per player ESPN lists as injured in each daily snapshot from 2026-09-08. A player missing from a snapshot was not listed that day. nba.injuries_latest is the newest snapshot. reported_at is UTC. player_id is NULL for players who have not yet played an NBA game, mostly rookies, and espn_athlete_id and player_name are always set.
- `nba.depth_charts` (2027 on): ESPN's depth chart in each daily snapshot from 2026-09-08. depth_rank 1 is the starter at the position, and one player can hold several positions. nba.depth_charts_latest is the newest snapshot. player_id is NULL for players who have not yet played an NBA game, mostly rookies, and espn_athlete_id and player_name are always set.
- `nba.playoff_series.season` (1948, 1954, 1956, 1957): Left out because their playoff games do not form an elimination bracket: 1954 opened with a round robin, and in 1948, 1956, and 1957 two teams played a tiebreaker game and then a series, which cannot be told apart by pairing teams.
- `nba.playoff_series.best_of` (current): Inferred from the winner's wins. In the latest season a round's format is taken from the previous season, so a series is decided once a team reaches that many wins, and winner_team_id is NULL until then.
- `nba.playoff_series.home_court_series_prob` (all): Assumes the home-court team hosts (best_of + 1) / 2 games and that games are independent. It uses elo_pre, whose fixed 100-point home edge is overconfident from 2015-16, and home_court_series_prob_fit uses the fitted Elo and edge from 2014-15.
- `nba.player_seasons` (all): Regular season only, like every bref.player_* table. Playoff player totals exist only from 1993-94, summed from nba.player_box, and no table holds them earlier.
- `nba.player_box.game_id` (1994-1996): Ten regular-season games have no box in any source: 199311050UTA, 199401030UTA, 199401270WSB, 199402260CLE, 199404070UTA, 199601270WSB, 199602070UTA, 199603240CLE, 199603290UTA, and 199604050CHH. ESPN lists them in its schedule but published no box, and no other source covers 1993-94 to 1995-96. nba.box_reconciliation lists them with team_box_missing.
- `nba.pbp.player_id` (1997-2015): On a coach's technical foul or ejection, player_id is the coach's NBA Stats id, which is not in nba.players. About 4,000 events from 1996-97 to 2014-15.

## More

`docs/dataset-guide.md` explains every source and table, and
`docs/data-dictionary.md` lists every column.
