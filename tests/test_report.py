from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import duckdb
import pytest

from nbalake.explore import macros, metrics
from nbalake.report import render, spec

CONTEXT = spec.load_context()
META = render.Meta(
    rendered_at=datetime(2026, 10, 24, 14, 52, tzinfo=UTC),
    lake_through=date(2026, 10, 23),
    metric_versions={"era_wins": 1},
)
ROWS = [(1988, "Michael Jordan", 28.2), (2009, "LeBron James", 24.0), (2024, "Nikola Jokić", 23.9)]


def raw(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "Best seasons",
        "title": "The best seasons since 1974",
        "finding": "Jordan leads.",
        "tiles": [{"label": "Best season", "value": "28.2", "note": "Jordan 1988"}],
        "blocks": [
            {
                "type": "line",
                "title": "Wins by season",
                "sql": "from seasons order by season",
                "x": "season",
                "y": "wins",
                "x_format": "season",
                "y_format": "num1",
            },
            {
                "type": "table",
                "title": "Top seasons",
                "sql": "from seasons order by wins desc",
                "columns": [
                    {"key": "season", "label": "Season", "format": "season"},
                    {"key": "player", "label": "Player", "format": "text"},
                    {"key": "wins", "label": "Wins", "format": "num1", "bar": True},
                ],
                "search": "player",
                "decades": "season",
            },
            {"type": "text", "title": "Note", "body": "Plain words."},
        ],
        "why": "Eras differ.",
        "method": [{"step": "Wins", "text": "BPM over replacement."}],
        "context": ["era_wins", "bpm", "basketball-reference"],
        "reading": [
            {"title": "BPM", "url": "https://www.basketball-reference.com/about/bpm2.html"}
        ],
    }
    return base | over


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    c.execute("CREATE TABLE seasons (season INTEGER, player VARCHAR, wins DOUBLE)")
    c.executemany("INSERT INTO seasons VALUES (?, ?, ?)", ROWS)
    return c


def build(con: duckdb.DuckDBPyConnection, meta: render.Meta = META, **over: Any) -> str:
    report = spec.parse(raw(**over), CONTEXT)
    return render.page(report, render.run(con, report), meta)


def embedded(html: str) -> dict[str, Any]:
    m = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html, re.S)
    assert m is not None
    return json.loads(m[1])


def test_each_block_carries_its_query_rows_inline(con: duckdb.DuckDBPyConnection) -> None:
    blocks = embedded(build(con))["blocks"]

    assert [b["type"] for b in blocks] == ["line", "table", "text"]
    assert [(r["season"], r["player"], r["wins"]) for r in blocks[1]["rows"]] == ROWS
    assert [r["season"] for r in blocks[0]["rows"]] == [1988, 2009, 2024]
    assert "rows" not in blocks[2]


def test_hostile_text_is_escaped_and_data_cannot_close_the_script_tag(
    con: duckdb.DuckDBPyConnection,
) -> None:
    con.execute("INSERT INTO seasons VALUES (2000, '</script><b>x</b>', 1.0)")

    html = build(con, title="<i>Best</i> & worst")

    assert "<i>Best</i>" not in html
    assert "&lt;i&gt;Best&lt;/i&gt; &amp; worst" in html
    assert html.count("</script>") == 2
    names = [r["player"] for r in embedded(html)["blocks"][1]["rows"]]
    assert "</script><b>x</b>" in names


def test_a_text_block_renders_each_blank_line_separated_paragraph_escaped(
    con: duckdb.DuckDBPyConnection,
) -> None:
    text = {
        "type": "text",
        "title": "How to read",
        "body": "Lift: points.\n\nShot <quality>: spots.",
    }

    html = build(con, blocks=[text])

    assert (
        '<p class="prose">Lift: points.</p><p class="prose">Shot &lt;quality&gt;: spots.</p>'
        in html
    )


def test_a_glossary_renders_between_the_tiles_and_the_first_block(
    con: duckdb.DuckDBPyConnection,
) -> None:
    glossary = {
        "intro": "Numbers are per 100 plays.",
        "terms": [
            {"term": "Lift", "definition": "Extra points <per> 100 plays."},
            {"term": "Creation", "definition": "Points off his passes."},
        ],
    }

    html = build(con, glossary=glossary)

    section = html[html.index('<section class="glossary">') :]
    section = section[: section.index("</section>")]
    assert "<h2>How to read the numbers</h2>" in section
    assert '<p class="prose">Numbers are per 100 plays.</p>' in section
    assert "<dt>Lift</dt><dd>Extra points &lt;per&gt; 100 plays.</dd>" in section
    assert html.index('class="tiles"') < html.index('class="glossary"')
    assert html.index('class="glossary"') < html.index('data-block="0"')


def test_a_report_without_a_glossary_renders_no_glossary_section(
    con: duckdb.DuckDBPyConnection,
) -> None:
    assert 'class="glossary"' not in build(con)


def test_a_glossary_term_without_a_definition_is_rejected_by_path() -> None:
    bad = raw(glossary={"terms": [{"term": "Lift"}]})

    with pytest.raises(spec.SpecError, match=r"spec\.glossary\.terms\[0\]\.definition"):
        spec.parse(bad, CONTEXT)


def test_the_queries_section_shows_each_query_formatted_and_highlighted(
    con: duckdb.DuckDBPyConnection,
) -> None:
    html = build(con)

    footer = html[html.index('<footer class="provenance">') :]
    assert footer.count('<code class="sql">') == 2
    assert (
        '<span class="sql-k">from</span> seasons\n<span class="sql-k">order</span>'
        ' <span class="sql-k">by</span> wins <span class="sql-k">desc</span>'
    ) in footer


def test_the_macros_a_query_calls_are_shown_with_their_definitions(
    con: duckdb.DuckDBPyConnection,
) -> None:
    body = "FROM seasons\nORDER BY wins DESC\nLIMIT n"
    sql = (
        "-- Top seasons by wins.\n-- example: from top_seasons()\n"
        f"CREATE OR REPLACE TEMP MACRO top_seasons(n := 2) AS TABLE\n{body}"
    )
    top = macros.Macro("top_seasons", "top_seasons(n := 2)", "Top seasons by wins.", "", sql, body)
    unused = macros.Macro("unused", "unused()", "Never called.", "", "SELECT 1", "SELECT 1")
    con.execute(sql)
    blocks = raw()["blocks"]
    blocks[1] = blocks[1] | {"sql": "from top_seasons(n := 3)"}

    html = build(con, replace(META, macros=(top, unused)), blocks=blocks)

    footer = html[html.index('<footer class="provenance">') :]
    assert "Macros these queries call" in footer
    assert "top_seasons(n := 2)" in footer
    assert "Top seasons by wins." in footer
    assert '<span class="sql-k">ORDER</span> <span class="sql-k">BY</span> wins' in footer
    assert "example:" not in footer
    assert "Never called." not in footer


def test_a_page_whose_queries_call_no_macro_has_no_macros_section(
    con: duckdb.DuckDBPyConnection,
) -> None:
    unused = macros.Macro("unused", "unused()", "Never called.", "", "SELECT 1", "SELECT 1")

    assert "Macros these queries call" not in build(con, replace(META, macros=(unused,)))


def test_a_hostile_query_is_escaped_in_the_queries_section(
    con: duckdb.DuckDBPyConnection,
) -> None:
    blocks = raw()["blocks"]
    blocks[1] = blocks[1] | {"sql": "select * from seasons where player <> '</code><b>x</b>'"}

    html = build(con, blocks=blocks)

    assert "<b>x</b>" not in html
    assert "&lt;/code&gt;&lt;b&gt;x&lt;/b&gt;" in html


def test_the_page_loads_nothing_from_the_network(con: duckdb.DuckDBPyConnection) -> None:
    html = build(con)

    assert "<link" not in html
    assert not re.search(r"<script[^>]*\ssrc=", html)
    assert all(u.startswith("data:") for u in re.findall(r"url\(([^)]*)\)", html))
    assert all(h.startswith("https://") for h in re.findall(r'href="([^"]*)"', html))
    assert "@import" not in html


def test_the_method_section_starts_collapsed_and_names_every_context_entry(
    con: duckdb.DuckDBPyConnection,
) -> None:
    html = build(con)

    assert '<details class="block method">' in html
    for key in ("era_wins", "bpm", "basketball-reference"):
        assert CONTEXT[key].title in html


def test_a_metric_in_context_puts_its_version_in_the_masthead(
    con: duckdb.DuckDBPyConnection,
) -> None:
    html = build(con)

    assert "era_wins v1" in html
    assert "2026-10-23" in html


def test_values_become_json_numbers_strings_and_iso_dates() -> None:
    c = duckdb.connect()
    report = spec.parse(
        raw(
            blocks=[
                {
                    "type": "table",
                    "title": "Types",
                    "sql": "select 1.25::DECIMAL(5,2) d, DATE '2016-06-19' g, "
                    "123456789012345::HUGEINT h, NULL::DOUBLE n",
                    "columns": [
                        {"key": "d", "label": "D", "format": "num2"},
                        {"key": "g", "label": "G", "format": "date"},
                        {"key": "h", "label": "H", "format": "int"},
                        {"key": "n", "label": "N", "format": "num1"},
                    ],
                }
            ]
        ),
        CONTEXT,
    )

    (rows,) = [b for b in render.run(c, report) if b is not None]

    assert rows == [{"d": 1.25, "g": "2016-06-19", "h": 123456789012345, "n": None}]


def test_a_named_column_missing_from_the_result_is_an_error(
    con: duckdb.DuckDBPyConnection,
) -> None:
    blocks = raw()["blocks"]
    blocks[1]["columns"][0]["key"] = "year"
    report = spec.parse(raw(blocks=blocks), CONTEXT)

    with pytest.raises(spec.SpecError, match=r"blocks\[1\].*year"):
        render.run(con, report)


def test_a_block_past_the_row_cap_is_an_error(
    con: duckdb.DuckDBPyConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(render, "MAX_ROWS", 2)
    report = spec.parse(raw(), CONTEXT)

    with pytest.raises(spec.SpecError, match="more than 2 rows"):
        render.run(con, report)


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"title": ""}, "title"),
        ({"blocks": [{"type": "pie", "title": "x"}]}, r"blocks\[0\].*pie"),
        ({"context": ["no-such-entry"]}, "no-such-entry"),
        ({"reading": [{"title": "x", "url": "javascript:alert(1)"}]}, "https"),
        ({"reading": [{"title": "x", "url": "http://example.com"}]}, "https"),
        ({"tiles": [{"label": "a", "value": "1", "note": "n"}] * 5}, "at most 4 tiles"),
        (
            {
                "blocks": [
                    {
                        "type": "line",
                        "title": "x",
                        "sql": "s",
                        "x": "a",
                        "y": "b",
                        "x_format": "season",
                        "y_format": "money",
                    }
                ]
            },
            "money",
        ),
        ({"surprise": 1}, "surprise"),
    ],
)
def test_a_malformed_spec_is_rejected_with_the_field_named(
    over: dict[str, Any], message: str
) -> None:
    with pytest.raises(spec.SpecError, match=message):
        spec.parse(raw(**over), CONTEXT)


def test_every_registered_metric_has_a_metric_context_entry() -> None:
    for m in metrics.registered():
        assert m.name in CONTEXT, f"add {m.name} to src/nbalake/report/context.toml"
        assert CONTEXT[m.name].kind is spec.Kind.METRIC


def test_every_context_link_is_public_https() -> None:
    for entry in CONTEXT.values():
        assert entry.text
        assert all(link.url.startswith("https://") for link in entry.links)


CHARTS = [
    {
        "type": "bar",
        "title": "Wins by player",
        "sql": "from seasons order by wins desc",
        "label": "player",
        "value": "wins",
        "value_format": "num1",
    },
    {
        "type": "scatter",
        "title": "Wins by season",
        "sql": "from seasons",
        "x": "season",
        "y": "wins",
        "label": "player",
        "x_format": "season",
        "y_format": "num1",
    },
    {
        "type": "multiples",
        "title": "Wins by season, per player",
        "sql": "from seasons",
        "facet": "player",
        "x": "season",
        "y": "wins",
        "x_format": "season",
        "y_format": "num1",
    },
]


@pytest.mark.parametrize("chart", CHARTS, ids=[c["type"] for c in CHARTS])
def test_each_chart_type_carries_its_fields_and_rows_but_not_its_sql(
    con: duckdb.DuckDBPyConnection, chart: dict[str, Any]
) -> None:
    html = build(con, blocks=[chart])

    (block,) = embedded(html)["blocks"]
    assert block["type"] == chart["type"]
    assert len(block["rows"]) == len(ROWS)
    assert {k: block[k] for k in chart if k not in ("title", "sql")} == {
        k: v for k, v in chart.items() if k not in ("title", "sql")
    }
    assert "sql" not in block
    assert 'data-block="0"' in html


@pytest.mark.parametrize("chart", CHARTS, ids=[c["type"] for c in CHARTS])
def test_a_chart_naming_a_column_its_query_lacks_is_an_error(
    con: duckdb.DuckDBPyConnection, chart: dict[str, Any]
) -> None:
    report = spec.parse(raw(blocks=[chart | {"sql": "select 1 as one"}]), CONTEXT)

    with pytest.raises(spec.SpecError, match=r"blocks\[0\] names .*which its query does not"):
        render.run(con, report)


def test_small_multiples_past_the_panel_cap_are_an_error(
    con: duckdb.DuckDBPyConnection,
) -> None:
    con.execute(
        "INSERT INTO seasons SELECT 2000, 'player ' || i, 1.0 FROM range(?) t(i)",
        [spec.MAX_PANELS],
    )
    report = spec.parse(raw(blocks=[CHARTS[2]]), CONTEXT)

    with pytest.raises(spec.SpecError, match=f"at most {spec.MAX_PANELS} fit"):
        render.run(con, report)


def test_an_unknown_block_type_lists_every_known_one() -> None:
    with pytest.raises(spec.SpecError, match="bar, scatter, multiples"):
        spec.parse(raw(blocks=[{"type": "pie", "title": "x"}]), CONTEXT)


def test_the_page_is_a_fragment_the_artifact_host_can_wrap(
    con: duckdb.DuckDBPyConnection,
) -> None:
    html = build(con)

    assert not re.search(r"<!doctype|</?(html|head|body)[\s>]", html, re.I)
    assert html.startswith('<meta charset="utf-8">')
    assert '<meta name="claude:viewport-fit-sides" content="cover">' in html
    title = re.search(r"<title>(.*?)</title>", html[:8192])
    assert title is not None and title[1] == "Best seasons"


def test_the_document_is_the_same_page_in_a_standards_mode_shell(
    con: duckdb.DuckDBPyConnection,
) -> None:
    fragment = build(con)

    doc = render.document(fragment)

    assert doc.startswith('<!doctype html>\n<html lang="en">\n')
    assert fragment in doc
    assert doc.rstrip().endswith("</html>")


@pytest.mark.parametrize(
    ("over", "message"),
    [
        ({"name": ""}, "name"),
        ({"name": "One two three four five six"}, "at most 5 words"),
        ({"artifact": "https://example.com/a"}, "claude.ai"),
    ],
)
def test_name_and_artifact_are_checked(over: dict[str, Any], message: str) -> None:
    with pytest.raises(spec.SpecError, match=message):
        spec.parse(raw(**over), CONTEXT)


def test_the_artifact_link_is_kept_but_never_drawn(con: duckdb.DuckDBPyConnection) -> None:
    url = "https://claude.ai/code/artifact/0b8e9a2c-1d2e-4f5a-9b6c-7d8e9f0a1b2c"
    report = spec.parse(raw(artifact=url), CONTEXT)

    assert report.artifact == url
    assert url not in render.page(report, render.run(con, report), META)


def test_a_report_reading_personal_use_data_carries_a_notice_naming_it_under_the_masthead(
    con: duckdb.DuckDBPyConnection,
) -> None:
    html = build(con, replace(META, personal=("nba.epm", "sdv.bbi_grades")))

    assert re.search(r'class="license-notice".*nba\.epm, sdv\.bbi_grades.*personal use', html, re.S)
    assert (
        html.index("</header>")
        < html.index('class="license-notice"')
        < html.index('<section class="finding">')
    )


def test_a_report_reading_only_open_tables_carries_no_notice(
    con: duckdb.DuckDBPyConnection,
) -> None:
    assert 'class="license-notice"' not in build(con)
