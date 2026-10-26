"""Runs a report's queries and renders it as one self-contained HTML page."""

from __future__ import annotations

import base64
import html
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from nbalake.explore.macros import Macro, called_by
from nbalake.report.spec import (
    MAX_PANELS,
    Bar,
    Block,
    Chart,
    Entry,
    Kind,
    Line,
    Multiples,
    Report,
    Scatter,
    SpecError,
    Table,
    Text,
)
from nbalake.report.sql import format_sql, highlight_sql

ASSETS = Path(__file__).parent / "assets"
MAX_ROWS = 2000
Rows = list[dict[str, Any]]
MACROS_NOTE = (
    "A name followed by parentheses, like career_postseason(), is a macro: a named query the"
    " lake ships, with its parameters and their defaults. Each one the queries use is defined"
    " here, with every macro it calls in turn after it."
)

LATIN = (
    "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,"
    "U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
)
LATIN_EXT = (
    "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,"
    "U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,"
    "U+A720-A7FF"
)
FACES = (
    ("Report Serif", "eb-garamond-latin-ext-400-normal", 400, "normal", LATIN_EXT),
    ("Report Serif", "eb-garamond-latin-ext-400-italic", 400, "italic", LATIN_EXT),
    ("Report Serif", "eb-garamond-latin-ext-700-normal", 700, "normal", LATIN_EXT),
    ("Report Serif", "eb-garamond-latin-400-normal", 400, "normal", LATIN),
    ("Report Serif", "eb-garamond-latin-400-italic", 400, "italic", LATIN),
    ("Report Serif", "eb-garamond-latin-700-normal", 700, "normal", LATIN),
    ("Report Mono", "hurmit-400", 400, "normal", None),
    ("Report Mono", "hurmit-700", 700, "normal", None),
)


@dataclass(frozen=True, slots=True)
class Meta:
    rendered_at: datetime
    lake_through: date
    metric_versions: dict[str, int]
    macros: tuple[Macro, ...] = ()
    personal: tuple[str, ...] = ()


def _json_value(v: Any) -> Any:
    match v:
        case Decimal():
            return float(v)
        case date():
            return v.isoformat()
        case _:
            return v


def _needed(block: Chart | Table) -> list[str]:
    match block:
        case Line(x=x, y=y):
            return [x, y]
        case Bar(label=label, value=value):
            return [label, value]
        case Scatter(x=x, y=y, label=label):
            return [x, y, label]
        case Multiples(facet=facet, x=x, y=y):
            return [facet, x, y]
        case Table(columns=columns, search=search, decades=decades):
            return [c.key for c in columns] + [k for k in (search, decades) if k]


def run(con: duckdb.DuckDBPyConnection, report: Report) -> list[Rows | None]:
    """Each block's rows in block order, None for a block without a query."""
    found: list[Rows | None] = []
    for i, block in enumerate(report.blocks):
        if isinstance(block, Text):
            found.append(None)
            continue
        try:
            cursor = con.execute(block.sql)
        except duckdb.Error as e:
            raise SpecError(f"spec.blocks[{i}].sql failed: {e}") from None
        names = [d[0] for d in cursor.description or ()]
        if missing := [k for k in _needed(block) if k not in names]:
            raise SpecError(
                f"spec.blocks[{i}] names {', '.join(missing)}, "
                f"which its query does not return ({', '.join(names)})"
            )
        rows = cursor.fetchmany(MAX_ROWS + 1)
        if len(rows) > MAX_ROWS:
            raise SpecError(f"spec.blocks[{i}] returns more than {MAX_ROWS} rows")
        if isinstance(block, Multiples):
            panels = {r[names.index(block.facet)] for r in rows}
            if len(panels) > MAX_PANELS:
                raise SpecError(
                    f"spec.blocks[{i}] has {len(panels)} panels, at most {MAX_PANELS} fit"
                )
        found.append([{n: _json_value(v) for n, v in zip(names, r, strict=True)} for r in rows])
    return found


def _block_payload(block: Block, rows: Rows | None) -> dict[str, Any]:
    fields = {
        k: v for k, v in asdict(block).items() if k not in ("title", "caption", "sql", "body")
    }
    return {"type": block.type, **fields} | ({} if rows is None else {"rows": rows})


def _fonts() -> str:
    faces: list[str] = []
    for family, name, weight, style, unicode_range in FACES:
        data = base64.b64encode((ASSETS / "fonts" / f"{name}.woff2").read_bytes()).decode()
        rng = f";unicode-range:{unicode_range}" if unicode_range else ""
        faces.append(
            f'@font-face{{font-family:"{family}";font-style:{style};font-weight:{weight};'
            f'font-display:block;src:url(data:font/woff2;base64,{data}) format("woff2"){rng}}}'
        )
    return "\n".join(faces)


def _e(text: str) -> str:
    return html.escape(text, quote=True)


def _block_html(i: int, block: Block) -> str:
    caption = (
        f'<p class="caption">{_e(block.caption)}</p>'
        if not isinstance(block, Text) and block.caption
        else ""
    )
    match block:
        case Multiples():
            body = '<div class="multiples"></div>'
        case Line() | Bar() | Scatter():
            body = '<figure class="chart"></figure>'
        case Table():
            controls = ""
            if block.search or block.decades:
                search = (
                    f'<input type="search" class="filter" '
                    f'placeholder="Filter by {_e(block.search)}" '
                    f'aria-label="Filter by {_e(block.search)}">'
                    if block.search
                    else ""
                )
                decades = (
                    '<select class="decade" aria-label="Decade">'
                    '<option value="">All decades</option></select>'
                    if block.decades
                    else ""
                )
                controls = (
                    f'<div class="controls">{search}{decades}<span class="count"></span></div>'
                )
            body = f'{controls}<div class="table-wrap"><table></table></div>'
        case Text():
            paragraphs = [p.strip() for p in block.body.split("\n\n") if p.strip()]
            body = "".join(f'<p class="prose">{_e(p)}</p>' for p in paragraphs)
    title = f"<h2>{_e(block.title)}</h2>"
    return f'<section class="block" data-block="{i}">{title}{caption}{body}</section>'


def _metric_labels(report: Report, meta: Meta) -> list[str]:
    return [
        f"{e.key} v{meta.metric_versions[e.key]}"
        for e in report.context
        if e.kind is Kind.METRIC and e.key in meta.metric_versions
    ]


def _entries(entries: list[Entry]) -> str:
    return "".join(f"<li><strong>{_e(e.title)}.</strong> {_e(e.text)}</li>" for e in entries)


def page(report: Report, results: list[Rows | None], meta: Meta) -> str:
    """The page as a fragment with no document tags, which an artifact host wraps itself."""
    metrics = _metric_labels(report, meta)
    fax = [
        meta.rendered_at.strftime("%d-%b-%Y %H:%M").upper(),
        "FROM: NBA LAKE",
        " ".join(m.upper() for m in metrics) or "NBA LAKE REPORT",
        "P.01/01",
    ]
    fields = [
        ("Date", meta.rendered_at.date().isoformat()),
        ("Lake through", meta.lake_through.isoformat()),
    ]
    fields += [("Metric", m) for m in metrics]
    if report.seasons:
        fields.append(("Seasons", report.seasons))
    masthead = "".join(f"<div><dt>{_e(k)}</dt><dd>{_e(v)}</dd></div>" for k, v in fields)
    tiles = "".join(
        f'<div class="tile"><div class="tile-label">{_e(t.label)}</div>'
        f'<div class="tile-value">{_e(t.value)}</div>'
        f'<div class="tile-note">{_e(t.note)}</div></div>'
        for t in report.tiles
    )
    glossary = ""
    if report.glossary:
        intro = report.glossary.intro
        lead = f'<p class="prose">{_e(intro)}</p>' if intro else ""
        terms = "".join(
            f"<div><dt>{_e(t.term)}</dt><dd>{_e(t.definition)}</dd></div>"
            for t in report.glossary.terms
        )
        glossary = (
            f'<section class="glossary"><h2>How to read the numbers</h2>{lead}'
            f'<dl class="terms">{terms}</dl></section>'
        )
    sources = [e for e in report.context if e.kind is Kind.SOURCE]
    terms = [e for e in report.context if e.kind is not Kind.SOURCE]
    links = list(report.reading) + [link for e in report.context for link in e.links]
    reading = "".join(
        f'<li><a href="{_e(link.url)}">{_e(link.title)}</a></li>' for link in dict.fromkeys(links)
    )
    queries = "".join(
        f'<pre><code class="sql">{highlight_sql(format_sql(b.sql))}</code></pre>'
        for b in report.blocks
        if not isinstance(b, Text)
    )
    used = called_by((b.sql for b in report.blocks if not isinstance(b, Text)), meta.macros)
    defined = "".join(
        f'<div class="macro"><div class="macro-name">{_e(m.signature)}</div>'
        f"<p>{_e(m.description)}</p>"
        f'<pre><code class="sql">{highlight_sql(m.body)}</code></pre></div>'
        for m in used
    )
    macro_section = (
        f"<details><summary>Macros these queries call</summary><p>{_e(MACROS_NOTE)}</p>"
        f"{defined}</details>"
        if used
        else ""
    )
    payload = json.dumps(
        {
            "blocks": [
                _block_payload(b, rows) for b, rows in zip(report.blocks, results, strict=True)
            ]
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    license_notice = (
        f'<p class="license-notice"><strong>Personal-use data.</strong> This report reads '
        f"{_e(', '.join(meta.personal))}, licensed for the owner's personal use. "
        f"Do not share it.</p>"
        if meta.personal
        else ""
    )
    method = "".join(f"<li><strong>{_e(s.step)}.</strong> {_e(s.text)}</li>" for s in report.method)
    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="claude:viewport-fit-sides" content="cover">
<title>{_e(report.name)}</title>
<style>{_fonts()}
{(ASSETS / "report.css").read_text(encoding="utf-8")}</style>
<div class="desk">
<div class="fax" aria-hidden="true">{"".join(f"<span>{_e(part)}</span>" for part in fax)}</div>
<article class="page">
<header class="masthead">
<div class="masthead-main"><div class="kicker">NBA Lake report</div>
<h1>{_e(report.title)}</h1></div>
<dl class="masthead-meta">{masthead}</dl>
<button class="theme-toggle" type="button" aria-label="Color theme">light</button>
</header>
{license_notice}
<section class="finding"><p>{_e(report.finding)}</p></section>
{f'<section class="tiles">{tiles}</section>' if tiles else ""}
{glossary}
{"".join(_block_html(i, b) for i, b in enumerate(report.blocks))}
<details class="block method">
<summary><h2>How this was measured</h2></summary>
<div class="method-body">
<h3>Why</h3><p>{_e(report.why)}</p>
<h3>Method</h3><ol>{method}</ol>
{f"<h3>Data</h3><ul>{_entries(sources)}</ul>" if sources else ""}
{f"<h3>Terms</h3><ul>{_entries(terms)}</ul>" if terms else ""}
{f"<h3>Further reading</h3><ul>{reading}</ul>" if reading else ""}
</div>
</details>
<footer class="provenance">
<details><summary>Queries behind this report</summary>{queries}</details>
{macro_section}
<p>Built from the NBA Lake. Numbers are quoted with the metric version and can move slightly
as new seasons arrive.</p>
<div class="end-mark">*** END OF REPORT ***</div>
</footer>
</article>
</div>
<script type="application/json" id="report-data">{payload}</script>
<script>{(ASSETS / "report.js").read_text(encoding="utf-8")}</script>
"""


def document(fragment: str) -> str:
    """The page as a standalone file: the fragment in a standards mode HTML shell."""
    return f'<!doctype html>\n<html lang="en">\n{fragment}</html>\n'
