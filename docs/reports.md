# Reports

A report is the shareable result of an analysis: one HTML file that opens in
any browser, offline, and explains itself to a reader who knows nothing
about the lake. An agent writes a JSON spec that says what the report shows,
and `nba report` runs its queries and renders the page. The look lives in
the renderer, so every report has the same design and a design fix reaches
every report rendered after it.

```
reports/<date>-<slug>.json  --nba report-->  reports/<date>-<slug>.html
  title, finding, tiles,         runs each block's SQL, read only
  glossary
  blocks: table, bar, line,      inlines the rows as JSON
    multiples, scatter, text
  why, method                    adds context blurbs from context.toml
  context keys, reading links    embeds fonts, CSS, and JS
```

Both files are committed. The spec is the source, and the HTML is its
rendering on the day the report was made.

## The page

A printed stat sheet with digital polish: EB Garamond for text, a
monospace (Hurmit, the Nerd Fonts build of Hermit, embedded as Report Mono)
for every number, black ink on a white sheet, black section bars. Light by
default, with a dark toggle. From the top:

1. A fax line: render time, `FROM: NBA LAKE`, the metrics and versions.
2. The masthead: title, then the date, the date the lake is current
   through, the metrics, and the seasons covered.
3. The finding: what the reader should take away, in a few sentences.
4. Up to four tiles: a label, one number, and a note.
5. How to read the numbers: an optional lead paragraph, then each term the
   page uses beside its definition.
6. Blocks, in order.
7. How this was measured, collapsed: why, the method, the data, the terms,
   and further reading.
8. The queries behind every block, collapsed, laid out one clause to a
   line and syntax highlighted, then the definition of every macro they
   call, directly or through another macro, callers first.

## The spec

```json
{
  "name": "Best Seasons Since 1974",
  "title": "The best seasons since 1974, translated into today's league",
  "finding": "Michael Jordan's 1987-88 is the most valuable season ...",
  "seasons": "1974-2026",
  "tiles": [{"label": "Best season", "value": "28.2", "note": "neutral wins, Jordan 1988"}],
  "glossary": {"intro": "Every number is a season measured against its own league ...",
               "terms": [{"term": "Neutral wins", "definition": "Wins the season would be worth ..."}]},
  "blocks": [
    {"type": "line", "title": "League strength by season", "caption": "...",
     "sql": "from league_strength() order by season",
     "x": "season", "y": "strength", "x_format": "season", "y_format": "signed2",
     "y_unit": "BPM", "baseline": "2025-26 = 0"},
    {"type": "table", "title": "Top 50 seasons by neutral wins",
     "sql": "from era_wins_season() order by neutral_wins desc limit 50",
     "columns": [{"key": "player", "label": "Player", "format": "text"},
                 {"key": "neutral_wins", "label": "Neutral wins", "format": "num1", "bar": true}],
     "search": "player", "decades": "season"},
    {"type": "text", "title": "What changed in 2005", "body": "..."}
  ],
  "why": "Raw totals do not compare across eras ...",
  "method": [{"step": "Impact against peers", "text": "BPM estimates ..."}],
  "context": ["era_wins", "bpm", "basketball-reference", "nba-stats"],
  "reading": [{"title": "Bridging different eras in sports", "url": "https://doi.org/..."}],
  "artifact": "https://claude.ai/artifact/..."
}
```

## Blocks

Pick a block by the job its data does. Every block has a `title`, an
optional `caption`, and, except `text`, a `sql`.

| Type | Job | Fields |
|---|---|---|
| `table` | rows to look up, sort, and filter, a top 20 or 50 | `columns` (`key`, `label`, `format`, `bar`), `search`, `decades` |
| `bar` | rank up to about 25 items by one number, negatives drawn left of zero | `label`, `value`, `value_format`, `value_unit` |
| `line` | one series over time | `x`, `y`, `x_format`, `y_format`, `y_unit`, `baseline` |
| `multiples` | the same series across up to 24 groups, a small line chart each on a shared y scale | `facet`, `x`, `y`, `x_format`, `y_format`, `y_unit`, `baseline` |
| `scatter` | how two measures relate across many items, each dot found by tapping, searching, or zooming | `x`, `y`, `label`, `x_format`, `y_format`, `x_unit`, `y_unit` |
| `text` | interpretation, a caveat, or the terms a reader needs before a chart, one paragraph per blank line | `body` |

- Rows draw in query order: a bar chart ranks as its SQL sorts, and a
  table starts in that order before the reader sorts it. Panels of
  `multiples` follow the order their facet first appears.
- A line breaks where its x skips, so a missed season shows as a gap.
- `baseline` draws the zero line and labels it, like `2025-26 = 0`.
- A scatter labels its most outlying dots and shows a tapped dot in a
  readout above the plot, where a thumb does not cover it. Zoom drags a box
  to rescale to it, and once 40 or fewer dots are in view they are listed
  below, highest y first.
- On a narrow screen a table keeps its leftmost columns that fit and folds
  the rest into a row a reader taps to open, so list columns most important
  first.
- Table `columns` name result columns in display order. `bar: true` draws a
  bar beside the value. `search` names a text column to filter on and
  `decades` a season column to filter by decade.

## Writing it

- `name` is the page's short name in browser tabs and the Claude app's
  gallery, at most five words. `title` is the headline on the page.

- Every text field is plain text. Write for someone who has never heard of
  the lake, and spell out a stat the first time it appears.
- Every column, tile, and chart value is defined before or where the reader
  first meets it. `glossary` holds those definitions: a lead paragraph that
  says what the numbers are about and their unit, then one term per measure
  the blocks show, in the order the reader meets them. Every report whose
  blocks carry a measure has one. The reader is a fan, so a term already
  common to fans, like rookie, starter, points, field goal percentage, or
  plus-minus, needs none, and defining it talks down to them. Define it
  only when the report uses it in a narrower sense than usual.
- A tile reads on its own: a plain label, the number, and a note saying
  what it counts. Process details like how a threshold was chosen, how
  stable a measure is, or which names were picked before the analysis
  belong in the method, not in a tile.
- The page speaks only about the result. No earlier version of the report,
  no internal names, and no analysis jargon a stranger cannot decode.
- The finding answers the question with its key numbers, and every number
  in it and in the tiles comes from a query you ran.
- `finding`, `why`, and `method` are this report's own words. Anything true
  of a dataset, metric, or stat in general belongs in `context.toml`.
- A block's SQL runs against the lake read only with the macros loaded,
  and returns at most 2,000 rows. A report shows a top 50, not a dataset.
- Write each `sql` as one line. The renderer lays it out for the queries
  section, a clause to a line with subqueries indented and long lists
  wrapped at 80 columns, and highlights it. It changes only whitespace, so
  the shown query is the one that ran.
- Formats: `text`, `int`, `num1`, `num2`, `num3`, `signed1`, `signed2`,
  `pct1` (0.475 as 47.5%), `rate3` (0.475 as .475), `season` (2016 as
  2015-16), `date`.
- `context` keys come from `src/nbalake/report/context.toml`. A metric key
  also puts the metric's version in the masthead.
- `reading` links and context links must be public `https` pages. The repo
  is private, so a link into it breaks for the reader.

## Context

`src/nbalake/report/context.toml` holds the reader-facing background, one
entry per dataset, metric, or stat: a title, two to four plain sentences,
and public links. Every registered metric must have an entry, and a test
fails when one is missing. When a report needs a source or stat that has
no entry, add the entry, then reference it.

## In the Claude app

The rendered page is also built to publish as a Claude artifact, so it
opens in the app on a phone. The artifact host supplies its own document
shell, so `page` renders the report without one, and the repo's file wraps
that same fragment in a standards mode shell. `--artifact <path>` writes
the fragment. The spec's optional `artifact` field keeps the published
link, so a later session updates that artifact instead of starting another.
The page keeps a 16px side gutter that clears a phone's safe areas, and
stays light unless the reader picks dark with its toggle.

## Personal-use data

A table fed by a paid source carries `license: personal` in `meta.catalog`,
and so does every curated model that reads one, directly or through another
model. `nba describe` says so. When any block's query reads such a table,
`nba report` prints the names on stderr and the page shows a notice under
the masthead naming them. The report skill asks the owner before it
publishes such a report.

## Commands

```bash
uv run nba report reports/2026-10-24-best-seasons.json   # writes the .html beside it
uv run nba report reports/2026-10-24-best-seasons.json --artifact /tmp/page.html
```

Open the HTML in a browser to check it. The page reads nothing from the
network: fonts, styles, script, and data are inside the file.
