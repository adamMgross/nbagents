# Metrics

A metric is a definition the owner has settled for something the lake does
not record directly, like career postseason achievement. It lives in the repo
as a methodology page and table macros, computes on demand from curated
tables, and carries a version so a number quoted today can be explained
later. Decision 34 records why.

```
src/nbalake/metrics/<name>/
  README.md     front matter (name, version, summary), then the methodology
  *.sql         table macros, one per file, with the macro header lines
tests/test_metric_<name>.py   what the definition must always do
```

`nba metrics` lists them, `nba metrics <name>` prints the methodology, and
their macros load into every `nba sql` and `nba py` session like the other
macros. `nba search` finds them by name and summary.

Ground a new metric in `docs/basketball/analysis.md` and
`docs/basketball/stats.md`: say which existing stat family it belongs to,
what it shares with them, and which blind spot it addresses.

## Developing one

1. **Name the question.** Write down, with the owner, what the metric should
   reward and what it must not punish, and two or three concrete cases it has
   to get right, like "losing the 2008 Finals to a great Celtics team keeps
   most of a title's worth". These cases are the acceptance tests.
2. **Prototype in scratch.** Use `nba py` or `nba sql --out`, and compute
   several variants side by side. Keep the prototype's per-row output in
   scratch for the parity check in step 5.
3. **Settle one definition.** Check every variant against the cases and show
   the owner the ranking each one gives. Variants the owner might still want
   become named parameters with the settled one as the default. Do not keep
   variants that failed a case.
4. **Port it to SQL macros.** Build on curated tables and the shipped macros
   (`nba.playoff_series`, `elo_game_prob`), not on staged tables or on
   reconstructions of something a curated table already holds. Expose the
   finest grain as its own macro, so a reader can see why a total is what it
   is, and build the totals on it.
   - Copy the parameters into a one-row `args` CTE, as every macro does, and
     raise with `error()` there on a value outside the allowed set.
   - Start the first table read from `args`, as in `FROM args a JOIN
     nba.playoff_series s ON ...`. DuckDB checks a table macro's tables when
     it is created unless a parameter binds first, and a test lake lacks
     most tables.
   - A macro that calls another needs nothing more. The loader orders macros
     by the calls in their bodies, across metrics too:
     `career_postseason_basic` builds on `career_postseason`'s
     `postseason_team_credit`. Add an option to a shared macro only with a
     default that leaves the owning metric's numbers unchanged.
5. **Check parity.** Compare the port with the prototype on every row, not
   on a top 20, and record the largest difference on the README.
6. **Write the README** from the template below. Every claim in it, like a
   rank or a percentage, comes from running the macros.
7. **Write the tests** in `tests/test_metric_<name>.py`, on small hand-built
   tables in an in-memory DuckDB. Test what the definition promises, not the
   numbers it happens to give: credit sums, monotonicity in the inputs that
   should matter, the owner's cases in miniature, argument errors.
8. **Register.** `uv run nbalake install-skills`, then `uv run pytest`.

## Stored or computed

Metrics compute on demand by default. Time the largest macro on the real
lake. Under a few seconds it stays a macro. Past that, or when other models
need to join to it, add a curated model whose SQL is `FROM
<macro>()` with a gate on its grain. The definition and the README do not
move.

## Versions

A change that moves any number raises `version` and adds a line under
Versions saying what changed and why. Quote numbers from a metric with its
version, like "career_postseason v1". A change that moves no number, like a
faster plan, keeps the version.

## README template

```
---
name: <folder name>
version: 1
summary: <one sentence: what it measures, from which season, and how>
---

# <Title>

## Question

<What it rewards, and what it must not punish.>

## Definition

<A small diagram, then numbered steps naming each column the macros return.>

## Why these choices

<The owner's cases and how version 1 does on each, from the macros.>

Rejected alternatives:

- <Each variant tried and the case it failed.>

## Limits

- <Seasons covered, data it cannot see, biases it carries.>

## Use

<Example nba sql calls, finest grain to total.>

## Versions

- 1, <date>: <the definition, and its parity with the prototype.>
```
