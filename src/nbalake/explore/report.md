---
name: report
description: Answer a basketball question from the NBA lake as a shareable report, one self-contained HTML page in the house stat sheet design with charts, sortable tables, and an explanation of the method and data. Use when the person asks for a report, or for an analysis they want to look at or share rather than a quick lookup.
argument-hint: <question>
---

# Report

The question: $ARGUMENTS

If no question came with the command, ask for one and stop. Read
`docs/reports.md` before writing the spec.

## 1. Answer it first

Read `docs/basketball/README.md` and `docs/basketball/analysis.md`, plus
any topic page the question touches, before the first query. Then work the
question with the `nba` CLI as the `nba-lake` skill describes:
`nba tables`, `nba describe` with its caveats, `nba find` for ids, macros
and `nba metrics` before hand-written joins, `--out` for intermediates.
Settle the answer before thinking about the page. Know the key numbers, how
they were computed, what the data cannot say, and which metric version they
come from.

## 2. Plan the page

- **Finding:** two to four sentences that answer the question with its key
  numbers. This is what the reader takes away if they read nothing else.
- **Tiles:** at most four headline numbers, each one a query result.
- **Glossary:** how to read the numbers. A lead paragraph on what every
  number is about and its unit, then each measure the tiles and blocks
  show, in the order a reader meets it, defined in a sentence or two.
  Define only what a fan would not already know (see the Terms check).
- **Blocks:** two to five, each with one job (the table in
  `docs/reports.md`):
  - a ranked list someone will scan or search: `table`, top 20 to 50
  - one number across up to 25 items: `bar`
  - one series over time: `line`
  - the same series across groups, players, or teams: `multiples`
  - two measures against each other: `scatter`
  - interpretation or a caveat the reader needs mid-page: `text`
- **Why and method:** for a reader who has never heard of the lake or the
  stat. Name what was measured, from what, and how, in plain words.
<!-- repo -->
- **Context:** the keys in `src/nbalake/report/context.toml` (`grep '^\['
  src/nbalake/report/context.toml`) for every dataset, metric, and stat the
  report rests on. When one is missing, add an entry in the same style:
  `kind`, `title`, two to four plain sentences, and only public `https`
  links you are sure exist.
<!-- end -->
<!-- app -->
- **Context:** the keys in the app's context file (`grep '^\['
  ~/.local/share/nbalake-app/_internal/nbalake/report/context.toml`) for
  every dataset, metric, and stat the report rests on. Use only keys that
  exist there. The file belongs to the app, so never edit it.
<!-- end -->

## 3. Write and render

1. Write `reports/<today>-<slug>.json`, the slug a few words of the
   question. `name` is the page's short name in browser tabs and the Claude
   app, two to four words that pick it out among many reports. Write each
   block's `sql` as one line without `\n`. The renderer formats and
   highlights every query in the queries section, so never lay one out by
   hand.
2. Render it, with the artifact form into your scratchpad:
   `uv run nba report reports/<today>-<slug>.json --artifact
   <scratchpad>/<slug>.html`. An error names the field or block at fault.
   Fix the spec and render again.
3. Look at the page once before publishing when a browser is available:
   `chromium --headless=new --hide-scrollbars --window-size=400,2400
   --screenshot=<scratchpad>/report.png file://$PWD/reports/<file>.html`,
   phone width since the owner often reads on a phone, then read the image.
   Check that labels do not collide, scales read sensibly, and the finding
   matches the charts. Make one pass of fixes, without a second look.

## 4. Review it as a stranger

The owner shares reports with basketball fans who have none of this
session's context: they know the game and its box score, not the lake or
analytics. Before publishing, read the rendered page top to bottom as that
person, using a taller screenshot or the spec in page order: finding,
tiles, blocks, why, method. Forget everything you learned while working.
Ask of each element:

- **Tiles.** Does the label say in plain words what the number is, and
  does the note say what it counts? A tile about the process, like how
  stable a measure is or how many names were picked in advance, belongs in
  the method. Replace it with a result.
- **Terms.** Is every column header, chart value, and coined name, like
  lift, creation, or openness, in the glossary or defined where the reader
  first meets it? Does the glossary define each term in words a fan
  knows, without leaning on another undefined term? Then the reverse:
  strike any definition of what a fan already knows, the words on a
  broadcast or a box score, like rookie, starter, draft pick, regular
  season, minutes, points, rebounds, assists, field goal percentage, or
  plus-minus. Defining them reads as talking down to the reader. Define
  the analytic and the coined (true shooting, usage, on minus off) and
  any common word the report uses in a narrower sense than usual.
- **Units.** Does every number say what it is per: per game, per 100
  plays, a share. Is zero or the baseline said where it matters?
- **Jargon.** Strike analysis vocabulary a stranger cannot decode:
  effective sample, odd against even seasons, shrinkage, fixed effects,
  internal table and column names. Say what it means instead, or move it
  to the method.
- **History.** Remove any mention of an earlier version of the report,
  what changed, or why an approach was dropped. The page states the
  result as it stands.
- **Order.** Answer, then the definitions it needs, then the main
  evidence, then secondary views, then surprises and limits. Each block
  has one job, and the page tells one story from the question to its
  answer.
- **Claims.** Is every sentence about a player backed by a number on the
  page or one you queried? Cut explanations you did not check.

Fix every finding in the spec, render again, and make one more check of
the changed parts only.

## 5. Publish it to the Claude app

If the render printed "personal-use data" or the page shows a personal-use
notice under its masthead, the report reads licensed paid tables. Do not
publish it until the owner says to, and ask them first.

When the Artifact tool is available, publish `<scratchpad>/<slug>.html`
so the owner can open the report in the Claude app:

- A spec without `artifact`: publish with `icon: "chart"` and a
  one-sentence `description`, then write the returned link into the spec
  as `"artifact"`.
- A spec with `artifact`: `action: "read"` on that link first, then publish
  with `url` set to it, so the same link updates.

## 6. Hand it over

Reply with the finding in a sentence or two, the artifact link, and the
path to the HTML file, which opens in any browser. Mention any caveat that
changes how the numbers read.
<!-- repo -->
Both repo files belong in the repo: commit them with the session's other
work.
<!-- end -->
<!-- app -->
Keep the spec beside the HTML, since rendering it again refreshes the
numbers.
<!-- end -->
