from __future__ import annotations

import html
import re

import duckdb
import pytest

from nbalake.report.sql import WIDTH, format_sql, highlight_sql

QUERIES = [
    "select rank, player, runs, first_season, last_season, credit, best_season, best_credit from"
    " career(min_runs := 2) order by rank limit 30",
    "with top as (select player_id, rank from career(min_runs := 2) where rank <= 8) select"
    " c.player, s.season, sum(s.credit) as credit from runs s join top t using (player_id) join"
    " career(min_runs := 2) c using (player_id) group by c.player, t.rank, s.season order by"
    " t.rank, s.season",
    "select player || ' ' || (season - 1) || '-' || right(season::varchar, 2) as run, credit"
    " from runs order by credit desc limit 20",
    "from runs where credit > 0 qualify row_number() over (partition by player_id order by"
    " credit desc) = 1 order by credit desc",
    "select player_id, count(*) filter (where runs.credit > 10) as big, string_agg(runs.player,"
    " ', ' order by season) as names from runs left join (from career(min_runs := 1)"
    " where rank < 3) c using (player_id) group by all order by player_id",
    "select 'a  b -- not a comment' as s, 1.5e2 as n -- trailing note\n from runs limit 1",
]


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    c.execute(
        "CREATE TABLE runs AS SELECT * FROM (VALUES (1, 'A', 2016, 59.4), (1, 'A', 2013, 55.3),"
        " (2, 'B', 1993, 68.6), (3, 'C', 2023, 60.8), (3, 'C', 2024, -1.0))"
        " t(player_id, player, season, credit)"
    )
    c.execute(
        "CREATE MACRO career(min_runs := 1) AS TABLE SELECT player_id, player,"
        " row_number() OVER (ORDER BY sum(credit) DESC) AS rank, count(*) AS runs,"
        " min(season) AS first_season, max(season) AS last_season, sum(credit) AS credit,"
        " arg_max(season, credit) AS best_season, max(credit) AS best_credit"
        " FROM runs GROUP BY player_id, player HAVING count(*) >= max(min_runs)"
    )
    return c


@pytest.mark.parametrize("sql", QUERIES)
def test_formatting_changes_only_whitespace(sql: str) -> None:
    assert re.sub(r"\s+", "", format_sql(sql)) == re.sub(r"\s+", "", sql)


@pytest.mark.parametrize("sql", QUERIES)
def test_a_formatted_query_returns_the_same_rows(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    assert con.execute(format_sql(sql)).fetchall() == con.execute(sql).fetchall()


@pytest.mark.parametrize("sql", QUERIES)
def test_formatting_is_idempotent(sql: str) -> None:
    assert format_sql(format_sql(sql)) == format_sql(sql)


def test_each_clause_starts_its_own_line() -> None:
    assert format_sql(QUERIES[1]).splitlines() == [
        "with top as (",
        "  select player_id, rank",
        "  from career(min_runs := 2)",
        "  where rank <= 8",
        ")",
        "select c.player, s.season, sum(s.credit) as credit",
        "from runs s",
        "join top t using (player_id)",
        "join career(min_runs := 2) c using (player_id)",
        "group by c.player, t.rank, s.season",
        "order by t.rank, s.season",
    ]


def test_function_and_window_parentheses_stay_on_one_line() -> None:
    lines = format_sql(QUERIES[3]).splitlines()

    assert lines == [
        "from runs",
        "where credit > 0",
        "qualify row_number() over (partition by player_id order by credit desc) = 1",
        "order by credit desc",
    ]
    assert "right(season::varchar, 2)" in format_sql(QUERIES[2])


def test_a_join_modifier_stays_with_its_join_and_a_subquery_indents() -> None:
    lines = format_sql(QUERIES[4]).splitlines()

    assert "left join (" in lines
    assert "  from career(min_runs := 1)" in lines
    assert "  where rank < 3" in lines
    assert ") c using (player_id)" in lines
    assert "string_agg(runs.player, ', ' order by season)" in format_sql(QUERIES[4])


def test_a_long_select_list_wraps_at_commas_within_the_width() -> None:
    lines = format_sql(QUERIES[0]).splitlines()

    assert all(len(line) <= WIDTH for line in lines)
    assert lines[0].startswith("select rank, player,")
    assert lines[1].startswith("  ")
    assert lines[2] == "from career(min_runs := 2)"


def test_a_line_comment_never_swallows_the_code_after_it() -> None:
    lines = format_sql(QUERIES[5]).splitlines()

    assert lines[0].endswith("-- trailing note")
    assert lines[1] == "from runs"


def test_highlighting_marks_tokens_and_keeps_the_text() -> None:
    sql = format_sql(QUERIES[2] + " -- note <b>")
    marked = highlight_sql(sql)

    assert html.unescape(re.sub(r"<[^>]+>", "", marked)) == sql
    assert '<span class="sql-k">select</span>' in marked
    assert '<span class="sql-f">right</span>(' in marked
    assert '<span class="sql-t">varchar</span>' in marked
    assert "<span class=\"sql-s\">'-'</span>" in marked
    assert '<span class="sql-n">20</span>' in marked
    assert '<span class="sql-c">-- note &lt;b&gt;</span>' in marked


def test_strings_and_comments_are_never_reformatted() -> None:
    sql = (
        "select 'from  where' as s, $$a  b$$ as d, $q$x  from$q$ as e /* select  from */ from runs"
    )

    assert "'from  where'" in format_sql(sql)
    assert "$$a  b$$" in format_sql(sql)
    assert "$q$x  from$q$" in format_sql(sql)
    assert "/* select  from */" in format_sql(sql)
    assert format_sql(sql).splitlines()[-1] == "from runs"
