from __future__ import annotations

import json
import resource
from dataclasses import replace
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner, Result

from nbalake import lake
from nbalake.curate import shipped_gates, shipped_steps
from nbalake.datasets import BY_NAME
from nbalake.explore import catalog, script, session
from nbalake.explore import query as q
from nbalake.explore.cli import app, caveat_lines
from nbalake.explore.entities import KEY_SQL, Entity, EntityKind, Tier, normalize, resolve
from nbalake.explore.render import Format, render
from nbalake.lake import Root
from nbalake.model import License
from nbalake.profile import TypeSource, personal_relations, type_source, write_catalog
from tests.curated import build_models, empty_lake, gate, insert, models, sources

REPO = Path(__file__).resolve().parent.parent
MODELS = (
    "franchises",
    "team_seasons",
    "teams",
    "espn_bref_links",
    "player_xref",
    "players",
    "player_seasons",
    "shots",
    "games",
    "player_aliases",
    "team_aliases",
)
GSW, NYK, CLE, OKC, CHI, UTA = (
    1610612744,
    1610612752,
    1610612739,
    1610612760,
    1610612741,
    1610612762,
)
FINALS_G7, WEST_G7, OLD_FINALS_G1 = "0041500407", "0041500317", "0049700084"
CURRY, LJ, LJ_ABA, SETH, JOKIC = 201939, 913, 9216443420461, 203552, 203999
runner = CliRunner()


@pytest.fixture(scope="module")
def lake_root(tmp_path_factory: pytest.TempPathFactory) -> Root:
    root = Root(tmp_path_factory.mktemp("explore") / "lake")
    con = empty_lake(root, sources(*MODELS))
    build_models(con, *MODELS)
    insert(
        con,
        "nba.players",
        [
            {
                "player_id": CURRY,
                "name": "Stephen Curry",
                "from_season": 2010,
                "to_season": 2026,
                "draft_year": 2009,
                "college": "Davidson",
            },
            {"player_id": SETH, "name": "Seth Curry", "from_season": 2014, "to_season": 2026},
            {"player_id": LJ, "name": "Larry Johnson", "from_season": 1992, "to_season": 2001},
            {"player_id": LJ_ABA, "name": "Larry Johnson", "from_season": 1978, "to_season": 1978},
            {"player_id": JOKIC, "name": "Nikola Jokić", "from_season": 2016, "to_season": 2026},
        ],
    )
    teams = [
        (GSW, "GSW", "Golden State Warriors"),
        (NYK, "NYK", "New York Knicks"),
        (CLE, "CLE", "Cleveland Cavaliers"),
        (OKC, "OKC", "Oklahoma City Thunder"),
        (CHI, "CHI", "Chicago Bulls"),
        (UTA, "UTA", "Utah Jazz"),
    ]
    insert(con, "nba.teams", [{"team_id": t, "name": n} for t, _, n in teams])
    insert(
        con,
        "nba.team_seasons",
        [
            {"season": season, "team_id": t, "abbreviation": a, "name": n}
            for season in (1998, 2001, 2016, 2026)
            for t, a, n in teams
        ]
        + [{"season": 2008, "team_id": OKC, "abbreviation": "SEA", "name": "Seattle SuperSonics"}],
    )
    insert(
        con,
        "nba.games",
        [
            game(FINALS_G7, 2016, "2016-06-19", GSW, CLE, 89, 93),
            game(WEST_G7, 2016, "2016-05-30", GSW, OKC, 96, 88),
            game("0049700070", 1998, "1998-05-20", CHI, NYK, 90, 80),
            game(OLD_FINALS_G1, 1998, "1998-06-05", UTA, CHI, 88, 93),
            game("0049700086", 1998, "1998-06-14", UTA, CHI, 86, 87),
            game("0049700050", 1998, "1998-05-01", UTA, NYK, 90, 80),
            game("0021500001", 2016, "2015-10-27", GSW, NYK, 111, 95, "regular"),
        ],
    )
    insert(
        con,
        "nba.player_seasons",
        [
            {"season": 2026, "lg": "NBA", "player_id": CURRY, "team_id": GSW, "g": 70, "pts": 1900},
            {"season": 2001, "lg": "NBA", "player_id": LJ, "team_id": NYK, "g": 65, "pts": 700},
        ],
    )
    insert(
        con,
        "sdv.nba_stats_shots",
        [
            {"game_id": "0021500001", "season": 2016, "person_id": CURRY, "shot_result": "Made"},
            {"game_id": "0021500002", "season": 2016, "person_id": CURRY, "shot_result": "Missed"},
            {"game_id": "0021700001", "season": 2018, "person_id": SETH, "shot_result": "Made"},
        ],
    )
    build_models(con, "entity_index")
    con.execute(
        "INSERT INTO meta.staged_units VALUES "
        "('sdv.nba_stats_shots', 'nba_stats_shots_2016.parquet', 'abc', NULL, 2, now()), "
        "('sdv.nba_stats_shots', 'nba_stats_shots_2018.parquet', 'def', NULL, 1, now())"
    )
    con.execute(
        "INSERT INTO meta.gate_results VALUES "
        "('r0', 'games_game_id_unique', 4, '[]', now() - INTERVAL 1 DAY), "
        "('r1', 'games_game_id_unique', 0, '[]', now()), "
        "('r1', 'games_home_and_away_differ', 2, '[]', now())"
    )
    write_catalog(
        con,
        {s.model.name: s.sql for s in shipped_steps(models(*MODELS, "entity_index"))},
        gate_sql={g.name: g.sql for g in shipped_gates("games_")},
    )
    con.close()
    return root


def game(
    game_id: str,
    season: int,
    day: str,
    home: int,
    away: int,
    hp: int,
    ap: int,
    season_type: str = "playoffs",
) -> dict:
    return {
        "game_id": game_id,
        "season": season,
        "game_date": day,
        "season_type": season_type,
        "home_team_id": home,
        "away_team_id": away,
        "home_pts": hp,
        "away_pts": ap,
    }


def nba(root: Root, *args: str) -> Result:
    return runner.invoke(app, [*args, "--root", str(root.path)], catch_exceptions=False)


def ok(result: Result) -> str:
    assert result.exit_code == 0, (result.stdout, result.stderr)
    return result.stdout


def md_rows(output: str) -> list[list[str]]:
    lines = [ln for ln in output.splitlines() if ln.startswith("|")][2:]
    return [[c.strip() for c in ln.strip("|").split(" | ")] for ln in lines]


def test_sql_prints_the_limit_and_says_on_stderr_that_more_rows_exist(lake_root: Root) -> None:
    result = nba(lake_root, "sql", "select i from range(1000) t(i)")

    assert len(md_rows(ok(result))) == 50
    assert "showing 50 rows, more exist" in result.stderr
    assert "--out <name>" in result.stderr


def test_sql_at_exactly_the_limit_prints_no_truncation_notice(lake_root: Root) -> None:
    result = nba(lake_root, "sql", "select i from range(50) t(i)")

    assert len(md_rows(ok(result))) == 50
    assert result.stderr == ""


def test_run_fetches_limit_plus_one_from_a_stream_that_never_ends(lake_root: Root) -> None:
    """A result of 10^12 rows cannot be materialized inside the five second deadline.

    Measured at 3 ms for the streamed fetch, so the deadline is over 1000x the cost. If run()
    ever fetched everything, or counted the result to decide truncation, it would time out.
    """
    con = session.connect(lake_root)

    result = q.run(con, "select i from range(1000000000000) t(i)", limit=50, timeout=5)

    assert result is not None
    assert len(result.rows) == 50
    assert result.truncated


def test_run_raises_query_timeout_when_the_deadline_passes(lake_root: Root) -> None:
    con = session.connect(lake_root)

    with pytest.raises(q.QueryTimeout, match="timeout"):
        q.run(con, "select count(*) from range(1000000000000)", limit=1, timeout=0.2)


def test_sql_errors_are_one_message_on_stderr_with_exit_1_and_duckdb_candidates(
    lake_root: Root,
) -> None:
    result = nba(lake_root, "sql", "select nope from nba.players")

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.startswith("error: Binder Error")
    assert "Candidate bindings" in result.stderr
    assert "Traceback" not in result.stderr


def test_sql_cannot_write_to_the_lake(lake_root: Root) -> None:
    result = nba(lake_root, "sql", "create table nba.x as select 1")

    assert result.exit_code == 1
    assert "read-only" in result.stderr or "read only" in result.stderr


def test_out_keeps_every_row_in_scratch_and_prints_the_count_not_the_rows(
    lake_root: Root,
) -> None:
    saved = nba(lake_root, "sql", "select i, i * 2 as j from range(500) t(i)", "--out", "evens")

    assert ok(saved).splitlines()[0] == "scratch.evens: 500 rows"
    assert md_rows(saved.stdout) == [["i", "BIGINT"], ["j", "BIGINT"]]
    total = nba(lake_root, "sql", "select sum(j) as s from scratch.evens", "-f", "csv")
    assert ok(total) == "s\n249500\n"
    ok(nba(lake_root, "sql", "drop table scratch.evens"))
    assert "scratch.evens" not in ok(nba(lake_root, "tables", "scratch"))


def test_out_rejects_a_name_that_is_not_a_plain_identifier(lake_root: Root) -> None:
    result = nba(lake_root, "sql", "select 1", "--out", "x; drop table y")

    assert result.exit_code == 1
    assert "plain table name" in result.stderr


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [
        (Format.MD, "| a | b |\n|---|---|\n| NULL | 1.235 |\n| x\\|y | 2.000 |"),
        (Format.JSONL, '{"a": null, "b": 1.23456}\n{"a": "x|y", "b": 2.0}'),
        (Format.CSV, "a,b\n,1.23456\nx|y,2.0"),
    ],
)
def test_render_formats_nulls_floats_and_pipes_per_format(fmt: Format, expected: str) -> None:
    assert render(("a", "b"), [(None, 1.23456), ("x|y", 2.0)], fmt) == expected


def test_render_cuts_long_cells_at_80_characters_unless_raw() -> None:
    long = "x" * 100

    assert render(("a",), [(long,)], Format.MD).splitlines()[2] == f"| {'x' * 77}... |"
    assert render(("a",), [(long,)], Format.MD, raw=True).splitlines()[2] == f"| {long} |"


def entity(id: str, label: str, *, aliases: tuple[str, ...] = (), sim: float = 0.5) -> Entity:
    return Entity(EntityKind.PLAYER, id, label, normalize(label), aliases, 2000, 2010, "", sim)


def test_resolve_prefers_an_exact_name_over_a_prefix_match() -> None:
    match = resolve([entity("1", "Stephen Curry"), entity("2", "Stephen Jackson")], "Stephen Curry")

    assert match.tier is Tier.EXACT
    assert match.resolved is not None and match.resolved.id == "1"


def test_resolve_returns_every_exact_match_when_two_players_share_a_name() -> None:
    match = resolve([entity("1", "Larry Johnson"), entity("2", "Larry Johnson")], "larry johnson")

    assert match.resolved is None
    assert {c.id for c in match.candidates} == {"1", "2"}


def test_resolve_takes_an_alias_before_a_word_prefix() -> None:
    curry = entity("1", "Stephen Curry", aliases=("steph",))

    match = resolve([curry, entity("2", "Stephen Jackson")], "Steph")

    assert match.tier is Tier.ALIAS
    assert match.resolved == curry


def test_resolve_matches_a_misspelling_only_above_the_fuzzy_threshold() -> None:
    close = entity("1", "Stephen Curry", sim=0.93)
    far = entity("2", "Seth Curtis", sim=0.85)

    match = resolve([close, far], "stephen cury")

    assert match.tier is Tier.FUZZY
    assert match.candidates == (close,)


def test_resolve_with_no_candidate_in_any_tier_is_an_empty_match() -> None:
    assert resolve([entity("1", "Stephen Curry")], "kareem").candidates == ()


@pytest.mark.parametrize(
    "name",
    [
        "Nikola Jokić",
        "Shaquille O'Neal",
        "J.R. Smith",
        "Shai Gilgeous-Alexander",
        "Dražen Petrović",
        "\u00d6mer A\u015f\u0131k",
        "  Metta  World Peace ",
    ],
)
def test_sql_key_matches_the_python_normalizer(name: str) -> None:
    sql = KEY_SQL.format(x="$name")
    got = duckdb.execute(f"SELECT {sql}", {"name": name}).fetchall()[0][0]
    assert got == normalize(name)


def test_find_player_resolves_an_accent_free_spelling(lake_root: Root) -> None:
    result = nba(lake_root, "find", "player", "jokic")

    assert md_rows(ok(result))[0][:2] == [str(JOKIC), "Nikola Jokić"]
    assert result.stderr == ""


def test_find_player_lists_both_players_who_share_a_name_with_their_seasons(
    lake_root: Root,
) -> None:
    result = nba(lake_root, "find", "player", "Larry Johnson")

    rows = md_rows(ok(result))
    assert [(r[0], r[2]) for r in rows] == [(str(LJ), "1992-2001"), (str(LJ_ABA), "1978")]
    assert "last team NYK" in rows[0][3]
    assert "2 players match" in result.stderr


def test_find_with_no_match_exits_1_with_a_hint(lake_root: Root) -> None:
    result = nba(lake_root, "find", "player", "zzzz qqqq")

    assert result.exit_code == 1
    assert "no player matches" in result.stderr


def test_tables_lists_curated_tables_and_one_line_per_staged_schema(lake_root: Root) -> None:
    rows = md_rows(ok(nba(lake_root, "tables")))

    names = [r[0] for r in rows]
    assert "nba.players" in names
    assert "bref.*" in names
    assert not any(n.startswith("bref.") and n != "bref.*" for n in names)


def test_describe_lists_columns_of_a_bare_curated_name(lake_root: Root) -> None:
    out = ok(nba(lake_root, "describe", "players"))

    assert out.startswith("# nba.players (table)")
    assert ["player_id", "HUGEINT"] in [r[:2] for r in md_rows(out)]
    assert "- grain: one row per player_id" in out


def test_describe_an_unknown_table_suggests_the_nearest_names(lake_root: Root) -> None:
    result = nba(lake_root, "describe", "nba.player")

    assert result.exit_code == 1
    assert "Did you mean nba.players" in result.stderr


def test_guide_prints_without_a_lake(tmp_path: Path) -> None:
    out = ok(runner.invoke(app, ["guide", "--help"]))

    assert "Examples" in out
    assert ok(runner.invoke(app, ["guide"])).startswith("# NBA lake")


def test_describe_a_view_counts_rows_and_seasons_from_its_staged_source(lake_root: Root) -> None:
    out = ok(nba(lake_root, "describe", "nba.shots"))

    assert "- rows: 3 (counted from sdv.nba_stats_shots)" in out
    assert "- seasons: 2016, 2018 (2 seasons, 1 to 2 rows each)" in out
    assert "game_id -> nba.games" in out and "player_id -> nba.players" in out


def test_discovery_reads_no_data_file_outside_meta(lake_root: Root, tmp_path: Path) -> None:
    """Every data file except the catalog's is moved away, so a read of one would raise.

    tables, describe, coverage, and search are the cheap first step of every session. If one
    reads a table to answer, its cost grows with the table, and nba.pbp makes it seconds.
    """
    data = lake_root.data
    before = {
        args: ok(nba(lake_root, *args))
        for args in (
            ("tables",),
            ("describe", "nba.shots"),
            ("describe", "nba.players"),
            ("tables", "sdv.nba_stats_shots"),
            ("coverage", "games"),
            ("coverage", "playoff attendance"),
            ("search", "playoff attendance"),
        )
    }
    moved = tmp_path / "moved"
    moved.mkdir()
    schemas = [d for d in data.iterdir() if d.name != "meta"]
    for d in schemas:
        d.rename(moved / d.name)
    try:
        broken = nba(lake_root, "sql", "select name from nba.players where name like 'S%'")
        assert broken.exit_code == 1
        after = {args: ok(nba(lake_root, *args)) for args in before}
    finally:
        for d in schemas:
            (moved / d.name).rename(d)
    assert after == before


def test_describe_lists_the_caveats_of_its_table(lake_root: Root) -> None:
    out = ok(nba(lake_root, "describe", "nba.shots"))

    caveat_lines = [ln for ln in out.splitlines() if ln.startswith("- nba.shots.")]
    assert [ln.split(" (")[0] for ln in caveat_lines] == [
        "- nba.shots.x_feet",
        "- nba.shots.season_type_id",
    ]


def test_search_finds_a_caveat_by_a_word_in_its_note(lake_root: Root) -> None:
    rows = md_rows(ok(nba(lake_root, "search", "elo")))

    assert ["caveat", "nba.team_games.elo_pre"] in [r[:2] for r in rows]


def test_search_finds_a_metric_by_a_word_in_its_summary_before_its_macros(lake_root: Root) -> None:
    rows = [r[:2] for r in md_rows(ok(nba(lake_root, "search", "achievement")))]

    assert rows[0] == ["metric", "career_postseason"]
    assert "career_postseason" in [name.partition("(")[0] for kind, name in rows if kind == "macro"]


def test_search_lists_curated_hits_before_staged_ones(lake_root: Root) -> None:
    names = [r[1] for r in md_rows(ok(nba(lake_root, "search", "shots")))]

    assert names.index("nba.shots") < names.index("sdv.nba_stats_shots")


def test_caveats_gate_flags_a_caveat_whose_table_or_column_is_missing(tmp_path: Path) -> None:
    con = empty_lake(Root(tmp_path / "lake"), [])
    build_models(con, "caveats")
    con.execute("CREATE TABLE nba.raptor (model VARCHAR)")
    con.execute("CREATE TABLE nba.player_seasons (season INTEGER)")

    flagged = {
        t for t, _ in con.execute(gate("search_caveats_name_a_table_and_column").sql).fetchall()
    }

    assert "nba.player_seasons" in flagged
    assert "nba.raptor" not in flagged


def test_find_player_resolves_a_nickname_from_the_alias_seed(lake_root: Root) -> None:
    result = nba(lake_root, "find", "player", "steph")

    assert [r[:2] for r in md_rows(ok(result))] == [[str(CURRY), "Stephen Curry"]]
    assert result.stderr == ""


def test_find_team_by_a_former_name_returns_the_franchise_with_every_name(
    lake_root: Root,
) -> None:
    result = nba(lake_root, "find", "team", "sonics")

    rows = md_rows(ok(result))
    assert {r[0] for r in rows} == {str(OKC)}
    assert [(r[1], r[2]) for r in rows] == [
        ("Seattle SuperSonics", "2008"),
        ("Oklahoma City Thunder", "1998-2026"),
    ]
    assert result.stderr == ""


def test_find_game_lists_the_finals_game_7_first_and_says_it_is_ambiguous(
    lake_root: Root,
) -> None:
    result = nba(lake_root, "find", "game", "finals 2016 game 7")

    rows = md_rows(ok(result))
    assert [r[0] for r in rows] == [FINALS_G7, WEST_G7]
    assert rows[0][1] == "2016-06-19 CLE @ GSW, Finals game 7"
    assert "2 games match" in result.stderr


def test_game_labels_find_the_finals_from_the_last_series_when_the_id_has_no_round(
    lake_root: Root,
) -> None:
    rows = md_rows(ok(nba(lake_root, "find", "game", "bulls jazz 1998 finals")))

    assert [(r[0], r[1].split(", ")[1]) for r in rows] == [
        (OLD_FINALS_G1, "Finals game 1"),
        ("0049700086", "Finals game 2"),
    ]


def test_every_index_key_is_the_python_normalization_of_its_label(lake_root: Root) -> None:
    con = session.connect(lake_root)

    pairs = con.execute("SELECT label, key FROM nba.entity_index").fetchall()

    assert pairs and all(key == normalize(label) for label, key in pairs)


def py(root: Root, source: str, *args: str) -> Result:
    return runner.invoke(
        app, ["py", "-", *args, "--root", str(root.path)], input=source, catch_exceptions=False
    )


def test_py_gives_the_script_the_lake_the_macros_and_polars(lake_root: Root) -> None:
    source = (
        "df = con.sql('select name from nba.players order by name').pl()\n"
        "print(df.height, type(df).__module__.split('.')[0])\n"
        "print(con.sql('select per_100(1, 4)').fetchall()[0][0])\n"
    )

    assert ok(py(lake_root, source)) == "5 polars\n25.0\n"


def test_py_two_steps_finish_from_scratch_without_rerunning_the_upstream_query(
    lake_root: Root, tmp_path: Path
) -> None:
    """The second step runs with the lake's data files moved away, so it can only read scratch."""
    ok(nba(lake_root, "sql", "select player_id, name from nba.players", "--out", "roster"))
    moved = tmp_path / "moved"
    moved.mkdir()
    schemas = [d for d in lake_root.data.iterdir() if d.name != "meta"]
    for d in schemas:
        d.rename(moved / d.name)
    try:
        out = ok(py(lake_root, "print(con.sql('select count(*) from scratch.roster').fetchall())"))
    finally:
        for d in schemas:
            (moved / d.name).rename(d)
        ok(nba(lake_root, "sql", "drop table scratch.roster"))
    assert out == "[(5,)]\n"


def test_py_error_shows_only_the_script_lines_and_exits_1(lake_root: Root) -> None:
    result = py(lake_root, "x = 1\ny = x / 0\n")

    assert result.exit_code == 1
    assert 'File "<stdin>", line 2' in result.stderr
    assert "ZeroDivisionError" in result.stderr
    assert "nbalake" not in result.stderr


@pytest.mark.parametrize(
    "source",
    [
        "while True:\n    pass\n",
        "con.sql('select count(*) from range(1000000000000)').fetchall()\n",
    ],
    ids=["python", "duckdb"],
)
def test_py_stops_at_the_timeout_in_python_and_in_a_query(lake_root: Root, source: str) -> None:
    result = py(lake_root, source, "--timeout", "0.5")

    assert result.exit_code == 1
    assert "timeout" in result.stderr


SPILLING_QUERY = (
    "select i, count(*) from (select (random() * 1e8)::bigint as i, repeat('x', 50) as s "
    "from range(3000000)) group by i order by 2 desc limit 1"
)


@pytest.fixture
def tiny_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lake, "CAPS", lake.Limits(memory="64MB", spill="1MB"))


def test_sql_past_the_cap_exits_1_with_one_line_naming_how_to_narrow(
    lake_root: Root, tiny_caps: None
) -> None:
    result = nba(lake_root, "sql", SPILLING_QUERY)

    assert result.exit_code == 1
    assert result.stderr == f"error: {session.OVER_CAP}\n"
    assert "--allow-spill SIZE" in session.OVER_CAP


def test_py_past_the_cap_exits_1_with_the_same_line(lake_root: Root, tiny_caps: None) -> None:
    result = py(lake_root, f"con.sql({SPILLING_QUERY!r}).fetchall()\n")

    assert result.exit_code == 1
    assert result.stderr == f"error: {session.OVER_CAP}\n"


@pytest.mark.parametrize("command", ["sql", "py"])
def test_allow_spill_lets_the_same_query_finish_for_that_run(
    lake_root: Root, tiny_caps: None, command: str
) -> None:
    if command == "sql":
        result = nba(lake_root, "sql", SPILLING_QUERY, "--allow-spill", "2GB")
    else:
        result = py(lake_root, f"con.sql({SPILLING_QUERY!r}).fetchall()\n", "--allow-spill", "2GB")

    assert result.exit_code == 0, result.stderr
    assert nba(lake_root, "sql", SPILLING_QUERY).exit_code == 1


def test_allow_spill_raises_only_the_spill_cap(lake_root: Root) -> None:
    settings = (
        "select current_setting('memory_limit') as memory, "
        "current_setting('max_temp_directory_size') as spill"
    )

    default = md_rows(ok(nba(lake_root, "sql", settings)))
    raised = md_rows(ok(nba(lake_root, "sql", settings, "--allow-spill", "12GB")))

    assert raised[0][0] == default[0][0]
    assert default[0][1] == "3.7 GiB"
    assert raised[0][1] == "11.1 GiB"


def test_py_cuts_long_output_and_says_so(lake_root: Root) -> None:
    result = py(lake_root, "print('x' * 50000)")

    assert len(result.stdout) == 20_000
    assert "output cut at 20,000 characters" in result.stderr


def test_describe_with_a_word_lists_only_the_columns_that_contain_it(lake_root: Root) -> None:
    out = ok(nba(lake_root, "describe", "players", "season"))

    assert [r[0] for r in md_rows(out)] == ["from_season", "to_season"]


def test_describe_a_staged_table_lists_types_without_empty_stat_columns(lake_root: Root) -> None:
    out = ok(nba(lake_root, "describe", "sdv.nba_stats_shots", "shot_"))

    assert "| column | type |\n|---|---|" in out
    assert all(len(r) == 2 for r in md_rows(out))


def test_each_command_closes_its_connection_so_scratch_can_be_attached_again(
    lake_root: Root,
) -> None:
    """Commands that leave a connection open hold scratch.duckdb, and the next attach fails."""
    for _ in range(3):
        ok(nba(lake_root, "sql", "select 1 as x", "--out", "reopened"))
    ok(nba(lake_root, "sql", "drop table scratch.reopened"))


@pytest.fixture(scope="module")
def seasons_root(tmp_path_factory: pytest.TempPathFactory) -> Root:
    root = Root(tmp_path_factory.mktemp("explain") / "lake")
    con = empty_lake(root, ["sdv.nba_stats_shots"])
    con.execute("ALTER TABLE sdv.nba_stats_shots SET PARTITIONED BY (season)")
    for season, ids in ((2016, ("0011500001", "0041500407")), (2018, ("0021700001",))):
        insert(con, "sdv.nba_stats_shots", [{"game_id": g, "season": season} for g in ids])
    con.close()
    return root


def test_explain_prints_files_read_and_rows_without_the_result_rows(seasons_root: Root) -> None:
    out = ok(
        nba(
            seasons_root,
            "sql",
            "select * from sdv.nba_stats_shots where season = 2016",
            "--explain",
        )
    )

    assert out.splitlines()[:2] == ["files read: 1", "rows from lake.sdv.nba_stats_shots: 2"]
    assert "0041500407" not in out
    assert "TABLE_SCAN  table: lake.sdv.nba_stats_shots  filters: (season = 2016)" in out


def test_explain_of_a_bare_game_id_filter_counts_every_season_file_it_opens(
    seasons_root: Root,
) -> None:
    out = ok(
        nba(
            seasons_root,
            "sql",
            "select * from sdv.nba_stats_shots where game_id = '0021700001'",
            "--explain",
        )
    )

    assert out.splitlines()[0] == "files read: 2"


def test_explain_cannot_be_combined_with_out(seasons_root: Root) -> None:
    result = nba(seasons_root, "sql", "select 1", "--explain", "--out", "x")

    assert result.exit_code == 1
    assert "--explain discards rows" in result.stderr


@pytest.mark.parametrize("fmt", ["md", "jsonl", "csv"])
def test_a_hand_written_explain_prints_its_plan_as_text_in_every_format(
    seasons_root: Root, fmt: str
) -> None:
    out = ok(nba(seasons_root, "sql", "explain select 1", "-f", fmt))

    assert "explain_key" not in out
    assert "Projection" in out and "\n" in out.strip()


def test_sql_prints_the_caveats_of_a_column_it_names_on_stderr_after_the_rows(
    lake_root: Root,
) -> None:
    query = f"select game_id, home_pts from nba.games where game_id = '{FINALS_G7}'"
    result = nba(lake_root, "sql", query)

    assert md_rows(ok(result)) == [[FINALS_G7, "89"]]
    assert "caveat" not in result.stdout
    assert result.stderr.splitlines() == [
        f"caveat {c.subject} ({c.seasons}): {c.note}"
        for c in catalog.caveats()
        if c.subject == "nba.games.game_id"
    ]


def test_sql_on_a_table_without_caveats_adds_nothing_to_stderr(lake_root: Root) -> None:
    result = nba(lake_root, "sql", "select count(*) from nba.players")

    assert ok(result)
    assert result.stderr == ""


def test_out_prints_the_caveats_of_the_columns_it_saved(lake_root: Root) -> None:
    result = nba(lake_root, "sql", "select season_type from nba.games", "--out", "types")

    assert ok(result)
    assert result.stderr.startswith("caveat nba.games.season_type (all): ")
    ok(nba(lake_root, "sql", "drop table scratch.types"))


def test_a_macro_call_reports_the_caveats_of_the_tables_its_body_reads() -> None:
    con = duckdb.connect()

    found = catalog.query_caveats(con, "from team_games_of(1610612744, 2016)", ["elo_pre"])

    assert "nba.team_games" in catalog.read_tables(con, "from against_the_spread(1, 2016)")
    assert [c.subject for c in found] == ["nba.team_games.elo_pre"]


def test_a_table_level_caveat_prints_without_naming_a_column() -> None:
    found = catalog.query_caveats(duckdb.connect(), "select count(*) from nba.l2m_calls", [])

    assert [c.subject for c in found] == ["nba.l2m_calls"]


def test_a_statement_duckdb_cannot_serialize_reports_no_caveats() -> None:
    assert catalog.query_caveats(duckdb.connect(), "drop table scratch.x", []) == ()


def test_caveat_lines_stop_at_four_and_name_describe_for_the_rest() -> None:
    impact = [c for c in catalog.caveats() if c.table == "nba.player_impact"]

    lines = caveat_lines(impact)

    assert len(impact) > 5
    assert len(lines) == 5
    assert lines[-1] == f"{len(impact) - 4} more caveats: nba describe nba.player_impact"


def test_describe_a_curated_table_names_its_sources_and_its_gates_last_results(
    lake_root: Root,
) -> None:
    out = ok(nba(lake_root, "describe", "nba.games"))

    built = next(ln for ln in out.splitlines() if ln.startswith("- built from: "))
    assert {"sdv.nba_stats_schedules", "nba.team_seasons", "fte.elo"} <= set(
        built.removeprefix("- built from: ").split(", ")
    )
    gates = next(ln for ln in out.splitlines() if ln.startswith("- gates: "))
    assert "failing at the last curate: games_home_and_away_differ (2 violations)" in gates
    assert "games_game_id_unique" not in gates


def test_describe_a_staged_table_names_its_upstream_and_units(lake_root: Root) -> None:
    out = ok(nba(lake_root, "describe", "sdv.nba_stats_shots"))

    assert "- upstream: github.com/sportsdataverse/sportsdataverse-data release " in out
    assert "- units staged: 2" in out


def test_describe_with_a_column_word_keeps_the_sources_and_gates(lake_root: Root) -> None:
    out = ok(nba(lake_root, "describe", "nba.games", "home"))

    assert "- built from: " in out and "- gates: " in out


def test_describe_a_scratch_table_shows_the_sql_its_out_ran_in_an_earlier_process(
    lake_root: Root,
) -> None:
    query = "select i from range(7) t(i)"
    ok(nba(lake_root, "sql", query, "--out", "sevens"))

    described = ok(nba(lake_root, "describe", "scratch.sevens"))
    listed = md_rows(ok(nba(lake_root, "tables", "scratch.")))

    assert f"Made by:\n\n    {query}" in described
    assert "Saved by nba sql --out at " in described
    assert [r[0] for r in listed] == ["scratch.sevens"]
    assert listed[0][-1].startswith("Saved by nba sql --out at ") and "7 rows" in listed[0][-1]
    ok(nba(lake_root, "sql", "drop table scratch.sevens"))


def test_a_second_out_to_the_same_name_replaces_its_provenance(lake_root: Root) -> None:
    ok(nba(lake_root, "sql", "select 1 as a", "--out", "again"))
    ok(nba(lake_root, "sql", "select 2 as b", "--out", "again"))

    assert "    select 2 as b" in ok(nba(lake_root, "describe", "scratch.again"))
    assert "select 1" not in ok(nba(lake_root, "describe", "scratch.again"))
    ok(nba(lake_root, "sql", "drop table scratch.again"))


def test_a_failed_out_leaves_no_table_and_no_provenance(lake_root: Root) -> None:
    ok(nba(lake_root, "sql", "select 1 as x", "--out", "saved_before_failure"))
    result = nba(lake_root, "sql", "select nope from nba.players", "--out", "broken")

    assert result.exit_code == 1
    rows = ok(
        nba(
            lake_root,
            "sql",
            "select count(*) from scratch.__provenance where name = 'broken'",
            "-f",
            "csv",
        )
    )
    assert rows == "count_star()\n0\n"


def test_a_scratch_macro_is_listed_under_yours_and_called_qualified(lake_root: Root) -> None:
    ok(nba(lake_root, "sql", "create or replace macro scratch.twice(x) as x * 2"))

    listed = ok(nba(lake_root, "macros"))
    called = ok(nba(lake_root, "sql", "select scratch.twice(21) as v", "-f", "csv"))

    assert "- twice(x), scalar: (x * 2)" in listed.split("## yours")[1].splitlines()
    assert called == "v\n42\n"
    ok(nba(lake_root, "sql", "drop macro scratch.twice"))
    assert "## yours" not in ok(nba(lake_root, "macros"))


@pytest.fixture
def tiny_python(monkeypatch: pytest.MonkeyPatch, tiny_caps: None) -> None:
    monkeypatch.setattr(script, "PYTHON_MEMORY", "128MB")


def test_py_materializing_a_frame_past_the_python_cap_exits_1_with_the_cap_line(
    lake_root: Root, tiny_python: None
) -> None:
    frame = "con.sql(\"select range i, repeat('x', 100) s from range(10000000)\").pl()\n"

    result = py(lake_root, frame)

    assert result.exit_code == 1
    assert result.stderr == f"error: {session.OVER_CAP}\n"


def test_py_python_memory_past_the_cap_exits_1_and_the_limit_is_lifted_after(
    lake_root: Root, tiny_python: None
) -> None:
    """A 1 GB bytearray succeeds without the data limit, so only the limit can refuse it."""
    before = resource.getrlimit(resource.RLIMIT_DATA)

    result = py(lake_root, "x = bytearray(2**30)\n")

    assert result.exit_code == 1
    assert result.stderr == f"error: {session.OVER_CAP}\n"
    assert resource.getrlimit(resource.RLIMIT_DATA) == before
    assert len(bytearray(2**30)) == 2**30


def test_py_under_the_python_cap_runs_unchanged(lake_root: Root, tiny_python: None) -> None:
    assert ok(py(lake_root, "print(len(bytearray(2**20)))\n")) == "1048576\n"


def test_py_runs_uncapped_where_proc_is_missing_as_on_macos(
    lake_root: Root, tiny_python: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(script, "PROC_STATUS", tmp_path / "missing")
    before = resource.getrlimit(resource.RLIMIT_DATA)

    assert ok(py(lake_root, "print(len(bytearray(2**30)))\n")) == f"{2**30}\n"
    assert resource.getrlimit(resource.RLIMIT_DATA) == before


@pytest.mark.parametrize(
    ("text", "size"), [("4GB", 4 * 10**9), ("128MB", 128 * 10**6), ("1.5GiB", 3 * 2**29)]
)
def test_size_bytes_reads_duckdb_size_strings(text: str, size: int) -> None:
    assert script.size_bytes(text) == size


def test_a_curated_view_reports_the_caveats_of_the_table_it_reads() -> None:
    found = catalog.query_caveats(duckdb.connect(), "from nba.injuries_latest", [])

    assert [c.subject for c in found] == ["nba.injuries"]


def test_describe_lists_seasons_per_season_type(lake_root: Root) -> None:
    out = ok(nba(lake_root, "describe", "nba.games"))
    assert "- playoffs: 1998, 2016 (2 seasons, 2 to 4 rows each)" in out
    assert "- regular: 2016 (1 seasons, 1 to 1 rows each)" in out


def test_describe_columns_prints_one_line_per_column_and_nothing_else(lake_root: Root) -> None:
    out = ok(nba(lake_root, "describe", "nba.games", "--columns"))
    assert out.splitlines()[0] == "| column | type | nulls | range or top values |"
    assert "Caveats" not in out and "rows:" not in out
    assert [r[0] for r in md_rows(out)][:3] == ["game_id", "season", "season_type"]


def test_a_search_miss_lists_tables_matching_each_word_with_the_named_season_type(
    lake_root: Root,
) -> None:
    result = nba(lake_root, "search", "playoff attendance")
    assert md_rows(ok(result)) == [
        ["nba.games", "playoffs", "1998, 2016 (2 seasons, 2 to 4 rows each)"]
    ]
    assert "nothing matches 'playoff attendance' as one phrase" in result.stderr
    assert "no curated table matching 'attendance' has playoffs rows before 1998" in result.stderr


def test_a_search_miss_with_no_table_matching_every_word_says_so(lake_root: Root) -> None:
    result = nba(lake_root, "search", "playoff zzyzx")
    assert ok(result) == ""
    assert "no curated table matches every word of 'zzyzx'" in result.stderr


def test_coverage_of_a_table_prints_each_season_type(lake_root: Root) -> None:
    rows = md_rows(ok(nba(lake_root, "coverage", "games")))
    assert rows == [
        ["playoffs", "1998, 2016 (2 seasons, 2 to 4 rows each)"],
        ["regular", "2016 (1 seasons, 1 to 1 rows each)"],
    ]


def test_coverage_of_a_table_without_season_type_prints_all_seasons(lake_root: Root) -> None:
    rows = md_rows(ok(nba(lake_root, "coverage", "player_seasons")))
    assert rows == [["all", "2001, 2026 (2 seasons, 1 to 1 rows each)"]]


def test_coverage_of_words_names_tables_with_no_season_type_column(lake_root: Root) -> None:
    rows = md_rows(ok(nba(lake_root, "coverage", "regular pts")))
    assert ["nba.games", "regular", "2016 (1 seasons, 1 to 1 rows each)"] in rows
    assert ["nba.player_seasons", "", "no season_type column"] in rows


def test_coverage_counts_a_new_season_and_season_type_without_code_changes(tmp_path: Path) -> None:
    root = Root(tmp_path / "lake")
    built = ("franchises", "team_seasons", "games")
    con = empty_lake(root, sources(*built))
    build_models(con, *built)
    sql = {s.model.name: s.sql for s in shipped_steps(models(*built))}
    insert(con, "nba.games", [game("g1", 2016, "2016-05-01", GSW, CLE, 100, 90)])
    write_catalog(con, sql)
    insert(con, "nba.games", [game("g2", 2031, "2031-04-20", GSW, CLE, 100, 90, "play-in")])
    write_catalog(con, sql)
    by_type = catalog.type_coverage(con, ("nba.games",))["nba.games"]
    con.close()
    assert [(c.season_type, [s.season for s in c.seasons]) for c in by_type] == [
        ("playoffs", [2016]),
        ("play-in", [2031]),
    ]


@pytest.mark.parametrize(
    ("schema", "columns", "games_exist", "expected"),
    [
        ("nba", {"game_id", "season", "season_type"}, True, TypeSource.GAMES),
        ("nba", {"game_id", "season"}, False, TypeSource.NONE),
        ("nba", {"season", "season_type"}, True, TypeSource.COLUMN),
        ("sdv", {"game_id", "season", "season_type"}, True, TypeSource.COLUMN),
        ("bref", {"season"}, True, TypeSource.NONE),
    ],
)
def test_a_curated_game_table_takes_its_season_type_from_games(
    schema: str, columns: set[str], games_exist: bool, expected: TypeSource
) -> None:
    assert type_source(schema, columns, games_exist) is expected


def test_coverage_of_a_game_table_without_season_type_uses_its_games_season_type(
    lake_root: Root,
) -> None:
    rows = md_rows(ok(nba(lake_root, "coverage", "shots")))
    assert rows == [["regular", "2016 (1 seasons, 1 to 1 rows each)"]]


def test_report_renders_the_spec_beside_it_with_the_lake_date(
    lake_root: Root, tmp_path: Path
) -> None:
    spec_path = tmp_path / "2026-10-24-finals.json"
    spec_path.write_text(
        json.dumps(
            {
                "name": "Game sevens",
                "title": "Game sevens",
                "finding": "Cleveland won at Golden State.",
                "blocks": [
                    {
                        "type": "table",
                        "title": "Games",
                        "sql": "select game_id, home_pts from nba.games order by game_id",
                        "columns": [
                            {"key": "game_id", "label": "Game", "format": "text"},
                            {"key": "home_pts", "label": "Home", "format": "int"},
                        ],
                    }
                ],
                "why": "To test.",
                "method": [{"step": "Read", "text": "One query."}],
                "context": ["nba-stats"],
            }
        )
    )

    out = ok(nba(lake_root, "report", str(spec_path)))

    page = spec_path.with_suffix(".html")
    assert out.strip() == str(page)
    assert page.read_text().startswith("<!doctype html>")
    assert "2016-06-19" in page.read_text()
    assert FINALS_G7 in page.read_text()


def test_report_with_artifact_also_writes_the_fragment_to_publish(
    lake_root: Root, tmp_path: Path
) -> None:
    spec_path = tmp_path / "2026-10-24-finals.json"
    spec_path.write_text(
        json.dumps(
            {
                "name": "Game sevens",
                "title": "Game sevens",
                "finding": "Cleveland won at Golden State.",
                "blocks": [{"type": "text", "title": "Note", "body": "Plain."}],
                "why": "To test.",
                "method": [{"step": "Read", "text": "None."}],
                "context": ["nba-stats"],
            }
        )
    )
    fragment = tmp_path / "publish.html"

    out = ok(nba(lake_root, "report", str(spec_path), "--artifact", str(fragment)))

    assert out.splitlines() == [str(spec_path.with_suffix(".html")), str(fragment)]
    assert fragment.read_text().startswith('<meta charset="utf-8">')
    assert fragment.read_text() in spec_path.with_suffix(".html").read_text()


def test_report_names_the_bad_field_and_exits_1(lake_root: Root, tmp_path: Path) -> None:
    spec_path = tmp_path / "bad.json"
    spec_path.write_text(json.dumps({"title": "x", "blocks": [{"type": "pie"}]}))

    result = nba(lake_root, "report", str(spec_path))

    assert result.exit_code == 1
    assert result.stderr.startswith("error: spec.")
    assert not spec_path.with_suffix(".html").exists()


def with_runs(root: Root, *runs: str) -> None:
    con = lake.connect(root)
    con.execute("DELETE FROM meta.runs")
    for r in runs:
        con.execute(f"INSERT INTO meta.runs VALUES ({r})")
    con.close()


def clear_runs(root: Root) -> None:
    con = lake.connect(root)
    con.execute("DELETE FROM meta.runs")
    con.close()


def test_discovery_says_what_the_lake_is_current_through_before_any_refresh_is_recorded(
    lake_root: Root,
) -> None:
    for args in (("tables",), ("describe", "nba.games")):
        result = nba(lake_root, *args)
        assert "lake: games through 2016-06-19, no refresh recorded" in result.stderr


def test_discovery_reports_a_failed_refresh_with_its_detail_and_staged_units_not_yet_curated(
    lake_root: Root,
) -> None:
    with_runs(
        lake_root,
        "'r1', 'refresh', TIMESTAMP '2000-01-01 03:00', TIMESTAMP '2000-01-01 03:10', false, "
        "'UnitsFailed: stage failed 2 units'",
    )
    try:
        err = nba(lake_root, "tables").stderr
    finally:
        clear_runs(lake_root)

    assert "last refresh 2000-01-01 03:10 FAILED: UnitsFailed: stage failed 2 units" in err
    assert "Staged since the last curate" not in err


def test_discovery_prints_the_refresh_time_and_flags_units_staged_after_the_last_curate(
    lake_root: Root,
) -> None:
    with_runs(
        lake_root,
        "'r1', 'refresh', TIMESTAMP '2000-01-01 03:00', TIMESTAMP '2000-01-01 03:10', true, NULL",
    )
    try:
        stale = nba(lake_root, "tables").stderr
        con = lake.connect(lake_root)
        con.execute(
            "INSERT INTO meta.runs VALUES "
            "('r2', 'curate', now(), now() + INTERVAL 1 HOUR, true, NULL)"
        )
        con.close()
        fresh = nba(lake_root, "tables").stderr
    finally:
        clear_runs(lake_root)

    assert (
        "lake: games through 2016-06-19, refreshed 2000-01-01 03:10. Staged since the last" in stale
    )
    assert "refreshed 2000-01-01 03:10" in fresh and "Staged since" not in fresh


def test_guide_skips_the_currency_line_when_the_root_holds_no_lake(tmp_path: Path) -> None:
    result = runner.invoke(app, ["guide", "--root", str(tmp_path / "none")])

    assert result.exit_code == 0 and result.stdout.startswith("# NBA lake")
    assert "lake:" not in result.stderr


def paid_lake(tmp_path: Path) -> Root:
    root = Root(tmp_path / "lake")
    built = ("franchises", "team_seasons", "games")
    con = empty_lake(root, sources(*built))
    build_models(con, *built)
    sql = {s.model.name: s.sql for s in shipped_steps(models(*built))}
    paid = replace(BY_NAME["sdv.nba_stats_schedules"], license=License.PERSONAL)
    write_catalog(con, sql, registry=[paid])
    con.close()
    return root


def test_a_curated_model_is_personal_use_when_it_reads_a_personal_dataset_and_describe_says_so(
    tmp_path: Path,
) -> None:
    root = paid_lake(tmp_path)
    con = session.connect(root)
    licenses = dict(con.execute("SELECT name, license FROM meta.catalog").fetchall())
    personal = catalog.personal_reads(
        con, ["select * from nba.games", "select * from nba.franchises"]
    )
    con.close()

    assert licenses["games"] == "personal" and licenses["nba_stats_schedules"] == "personal"
    assert licenses["franchises"] == "open"
    assert personal == ("nba.games",)
    assert "- license: personal use only, do not share" in ok(nba(root, "describe", "nba.games"))
    assert "license: personal" not in ok(nba(root, "describe", "nba.franchises"))


def test_a_model_reading_a_personal_model_is_personal_through_any_depth() -> None:
    reads = {"a": ["sdv.paid"], "b": ["nba.a"], "c": ["nba.b", "nba.open"], "d": ["nba.open"]}

    assert personal_relations(reads, {"sdv.paid"}) == {"sdv.paid", "nba.a", "nba.b", "nba.c"}
