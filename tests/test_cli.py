from __future__ import annotations

import hashlib
import re

import httpx
import pytest
from typer.core import TyperGroup
from typer.main import get_command
from typer.testing import CliRunner, Result

import nbalake.curate
from nbalake import capture as cap
from nbalake import datasets, lake, preflight
from nbalake.cli import SETUP_RESUMES, app
from nbalake.lake import Root, table_exists
from nbalake.model import ReleaseAssets
from tests.conftest import FakeUpstream, parquet_bytes
from tests.curated import GATES, STEPS

COMMANDS = (
    "datasets",
    "capture",
    "stage",
    "curate",
    "vacuum",
    "refresh",
    "setup",
    "status",
    "sql",
    "ui",
    "dictionary",
    "install-skills",
)
LAKELESS_COMMANDS = ("install-skills",)
WRITE_COMMANDS = ("capture", "stage", "curate", "vacuum", "refresh", "setup")
SCHEDULES = "sdv.nba_stats_schedules"
PBP = "sdv.espn_nba_pbp"
TEAM_BOX = "sdv.nba_stats_team_boxscores"
ANSI = re.compile(r"\x1b\[[0-9;]*m")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

GAMES = [
    {
        "season": 2026,
        "season_type": "Regular Season",
        "game_id": "0022500001",
        "game_date": "2025-10-21",
        "home_team_id": 1610612761,
        "home_team_abbreviation": "TOR",
        "away_team_id": 1610612766,
        "away_team_abbreviation": "CHA",
        "home_pts": 110,
        "away_pts": 102,
    },
    {
        "season": 2026,
        "season_type": "Regular Season",
        "game_id": "0022500002",
        "game_date": "2025-10-22",
        "home_team_id": 1610612747,
        "home_team_abbreviation": "LAL",
        "away_team_id": 1610612744,
        "away_team_abbreviation": "GSW",
        "home_pts": 99,
        "away_pts": 105,
    },
]


def team_box_rows(games: list[dict], *, home_pts_error: int = 0) -> list[dict]:
    rows = []
    for g in games:
        for side in ("home", "away"):
            points = g[f"{side}_pts"] + (home_pts_error if side == "home" else 0)
            rows.append(
                {
                    "game_id": g["game_id"],
                    "team_id": g[f"{side}_team_id"],
                    "points": points,
                    "season": g["season"],
                }
            )
    return rows


TEAM_BOX_ROWS = team_box_rows(GAMES)

runner = CliRunner()


@pytest.fixture(autouse=True)
def wide_console(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "250")


@pytest.fixture(autouse=True)
def tracer_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nbalake.curate, "shipped_steps", lambda: STEPS)
    monkeypatch.setattr(nbalake.curate, "shipped_gates", lambda: GATES)


@pytest.fixture(autouse=True)
def roomy_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "free_bytes", lambda path: preflight.REQUIRED_BYTES)


@pytest.fixture
def offline(upstream: FakeUpstream, monkeypatch: pytest.MonkeyPatch) -> FakeUpstream:
    def make_client(timeout: float = 120.0) -> httpx.Client:
        return httpx.Client(transport=upstream.transport, follow_redirects=True)

    monkeypatch.setattr(cap, "make_client", make_client)
    return upstream


def publish(upstream: FakeUpstream, name: str, filename: str, rows: list[dict], **kw: str) -> bytes:
    fetch = datasets.BY_NAME[name].fetch
    assert isinstance(fetch, ReleaseAssets)
    payload = parquet_bytes(rows)
    upstream.add_release_asset(fetch.repo, fetch.tag, filename, payload, **kw)
    return payload


def cli(root: Root, *args: str, catch_exceptions: bool = False) -> Result:
    return runner.invoke(app, [*args, "--root", str(root.path)], catch_exceptions=catch_exceptions)


def ok(result: Result) -> str:
    assert result.exit_code == 0, (result.stdout, result.stderr, result.exception)
    assert result.stderr == ""
    return result.stdout


def lines(output: str) -> list[str]:
    return [line for line in output.splitlines() if line]


def table_rows(output: str) -> list[list[str]]:
    return [
        [cell.strip() for cell in line.strip().strip("│").split("│")]
        for line in output.splitlines()
        if line.startswith("│")
    ]


def row_for(output: str, first_cell: str) -> list[str]:
    return next(r for r in table_rows(output) if r[0] == first_cell)


def query(root: Root, sql: str, params: list[object] | None = None) -> list[tuple]:
    con = lake.connect(root, read_only=True)
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def test_datasets_lists_every_registered_dataset_with_zero_raw_units(root: Root) -> None:
    out = ok(cli(root, "datasets"))

    assert [r[0] for r in table_rows(out) if r[0]] == [d.name for d in datasets.ALL]
    for d in datasets.ALL:
        assert row_for(out, d.name)[1:3] == [d.partition or "", "0"]
    assert not root.path.exists()


def test_datasets_with_a_name_lists_only_that_dataset(root: Root) -> None:
    out = ok(cli(root, "datasets", "sdv.nba_stats_pbp"))

    assert [r[0] for r in table_rows(out)] == ["sdv.nba_stats_pbp"]


def test_datasets_rejects_an_unknown_name_on_stderr_with_exit_2(root: Root) -> None:
    result = cli(root, "datasets", "nope")

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr == "no dataset matches 'nope'\n"


def test_capture_stores_the_asset_in_raw_and_skips_it_on_the_next_run(
    root: Root, offline: FakeUpstream
) -> None:
    payload = publish(offline, TEAM_BOX, "team_boxscores_2026.parquet", TEAM_BOX_ROWS)
    url = f"{datasets.BY_NAME[TEAM_BOX].fetch.url_prefix}team_boxscores_2026.parquet"

    first = ok(cli(root, "capture", TEAM_BOX))
    second = ok(cli(root, "capture", TEAM_BOX))

    (first_line,) = lines(first)
    (second_line,) = lines(second)
    assert re.fullmatch(r"fetched 1 units, 0\.0 MB, skipped 0 up to date, [\d.,]+s", first_line)
    assert re.fullmatch(r"fetched 0 units, 0\.0 MB, skipped 1 up to date, [\d.,]+s", second_line)
    assert root.blob(hashlib.sha256(payload).hexdigest()).read_bytes() == payload
    assert len(root.fetches.read_text().splitlines()) == 1
    assert offline.request_log.count(url) == 1
    assert row_for(ok(cli(root, "datasets", TEAM_BOX)), TEAM_BOX)[2] == "1"
    assert not root.catalog.exists()


def test_capture_reports_a_failed_download_on_stderr_and_exits_1(
    root: Root, offline: FakeUpstream
) -> None:
    publish(offline, TEAM_BOX, "team_boxscores_2026.parquet", TEAM_BOX_ROWS)
    url = f"{datasets.BY_NAME[TEAM_BOX].fetch.url_prefix}team_boxscores_2026.parquet"
    offline.fail_next(url)

    result = cli(root, "capture", TEAM_BOX)

    assert result.exit_code == 1
    (summary,) = lines(result.stdout)
    assert summary.startswith("fetched 0 units, 0.0 MB, skipped 0 up to date")
    assert result.stderr.startswith(f"failed {url}: ReadError")
    assert not root.fetches.exists()


def test_stage_loads_new_units_and_reports_unchanged_on_rerun(
    root: Root, offline: FakeUpstream
) -> None:
    publish(offline, TEAM_BOX, "team_boxscores_2026.parquet", TEAM_BOX_ROWS)
    ok(cli(root, "capture", TEAM_BOX))

    first = ok(cli(root, "stage", TEAM_BOX, "sdv.nba_stats_pbp"))
    second = ok(cli(root, "stage", TEAM_BOX, "sdv.nba_stats_pbp"))

    assert lines(first) == [
        f"{TEAM_BOX}: loaded 1 units, {len(TEAM_BOX_ROWS)} rows",
        "nothing in raw for: sdv.nba_stats_pbp",
    ]
    assert lines(second) == [
        "unchanged: 1 datasets",
        "nothing in raw for: sdv.nba_stats_pbp",
    ]
    assert query(root, f"SELECT count(*) FROM {TEAM_BOX}") == [(len(TEAM_BOX_ROWS),)]
    assert query(root, "SELECT command, ok FROM meta.runs ORDER BY started_at") == [
        ("stage", True),
        ("stage", True),
    ]


def test_status_reports_raw_staged_and_run_state_from_the_env_root(
    root: Root, offline: FakeUpstream
) -> None:
    publish(offline, TEAM_BOX, "team_boxscores_2026.parquet", TEAM_BOX_ROWS)
    ok(cli(root, "capture", TEAM_BOX))
    ok(cli(root, "stage", TEAM_BOX))

    out = ok(runner.invoke(app, ["status", "--datasets"], env={"NBALAKE_ROOT": str(root.path)}))

    dataset_row = row_for(out, TEAM_BOX)
    assert dataset_row[1:4] == ["1", "1", str(len(TEAM_BOX_ROWS))]
    assert TIMESTAMP.fullmatch(dataset_row[4])
    assert row_for(out, SCHEDULES)[1:] == ["0", "0", "0", ""]
    assert f"raw: 1 fetches, 0.00 GB at {root.path.resolve() / 'raw'}" in out.splitlines()
    (run,) = [r for r in table_rows(out) if r[1:2] == ["stage"]]
    assert run[4:] == ["True", ""]
    assert TIMESTAMP.fullmatch(run[2])
    assert "snapshots: no missing capture dates" in out.splitlines()


def test_status_leads_with_currency_and_runs_and_lists_datasets_only_on_request(
    root: Root, offline: FakeUpstream
) -> None:
    publish(offline, TEAM_BOX, "team_boxscores_2026.parquet", TEAM_BOX_ROWS)
    ok(cli(root, "capture", TEAM_BOX))
    ok(cli(root, "stage", TEAM_BOX))
    env = {"NBALAKE_ROOT": str(root.path)}

    out = ok(runner.invoke(app, ["status"], env=env))

    lines = out.splitlines()
    assert lines[0].startswith("lake: no catalog yet, no refresh recorded")
    assert any("stage" in ln for ln in lines[1:8])
    assert "gates: 0 checked, 0 failing" in lines
    assert TEAM_BOX not in out and SCHEDULES not in out
    assert TEAM_BOX in ok(runner.invoke(app, ["status", "--datasets"], env=env))


def test_sql_prints_the_result_set(root: Root, offline: FakeUpstream) -> None:
    publish(offline, TEAM_BOX, "team_boxscores_2026.parquet", TEAM_BOX_ROWS)
    ok(cli(root, "capture", TEAM_BOX))
    ok(cli(root, "stage", TEAM_BOX))

    out = ok(cli(root, "sql", f"select count(*) as n from {TEAM_BOX}"))

    assert "n" in out.splitlines()[1]
    assert table_rows(out) == [[str(len(TEAM_BOX_ROWS))]]


def test_sql_has_the_nba_macros(root: Root) -> None:
    lake.connect(root).close()

    out = ok(cli(root, "sql", "select per_100(1, 4) as rate"))

    assert "25.0" in out


def test_sql_statement_without_a_result_set_prints_nothing(root: Root) -> None:
    lake.connect(root).close()

    out = ok(cli(root, "sql", "SET threads TO 1"))

    assert out == ""


def test_curate_without_the_schedule_table_fails_and_records_the_run(root: Root) -> None:
    result = cli(root, "curate", catch_exceptions=True)

    assert result.exit_code == 1
    assert result.exception is not None
    ((command, ok_, detail),) = query(root, "SELECT command, ok, detail FROM meta.runs")
    assert (command, ok_) == ("curate", False)
    assert detail.startswith("CatalogException") and "nba_stats_schedules" in detail
    assert query(root, "SELECT count(*) FROM meta.gate_results") == [(0,)]
    con = lake.connect(root, read_only=True)
    try:
        assert not table_exists(con, "nba", "games")
    finally:
        con.close()


def test_refresh_captures_stages_and_curates_in_one_recorded_run(
    root: Root, offline: FakeUpstream
) -> None:
    publish(offline, SCHEDULES, "nba_schedule_2026.parquet", GAMES)
    publish(offline, TEAM_BOX, "team_boxscores_2026.parquet", TEAM_BOX_ROWS)

    out = ok(cli(root, "refresh", SCHEDULES, TEAM_BOX))

    assert lines(out)[:-2] == [
        "captured 2 new units, 0 up to date",
        f"{SCHEDULES}: loaded 1 units, {len(GAMES)} rows",
        f"{TEAM_BOX}: loaded 1 units, {len(TEAM_BOX_ROWS)} rows",
        f"nba.games: {len(GAMES)} rows",
        "gate games_game_id_unique: pass",
        "gate games_scores_agree_with_team_box: pass",
    ]
    assert all(line.startswith("vacuum: ") for line in lines(out)[-2:])
    ((run_id, command, ok_),) = query(root, "SELECT run_id, command, ok FROM meta.runs")
    assert (command, ok_) == ("refresh", True)
    assert query(
        root,
        "SELECT gate, violations FROM meta.gate_results WHERE run_id = ? ORDER BY gate",
        [run_id],
    ) == [("games_game_id_unique", 0), ("games_scores_agree_with_team_box", 0)]
    assert query(root, "SELECT game_id, winner_team_id FROM nba.games ORDER BY game_id") == [
        ("0022500001", 1610612761),
        ("0022500002", 1610612744),
    ]


def test_setup_builds_the_lake_then_proves_it_answers_a_query(
    root: Root, offline: FakeUpstream
) -> None:
    publish(offline, SCHEDULES, "nba_schedule_2026.parquet", GAMES)
    publish(offline, TEAM_BOX, "team_boxscores_2026.parquet", TEAM_BOX_ROWS)

    out = ok(cli(root, "setup", SCHEDULES, TEAM_BOX))

    assert lines(out)[0] == "captured 2 new units, 0 up to date"
    assert lines(out)[-1] == f"ready: {len(GAMES)} games from 2026 to 2026 in {root.path}"
    assert query(root, "SELECT command, ok FROM meta.runs") == [("setup", True)]


def test_setup_with_too_little_disk_exits_2_before_writing_anything(
    root: Root, offline: FakeUpstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(preflight, "free_bytes", lambda path: 0)

    result = cli(root, "setup", SCHEDULES)

    assert result.exit_code == 2
    assert "NBALAKE_ROOT" in result.stderr
    assert not root.catalog.exists()


def test_setup_with_a_failed_download_says_a_rerun_resumes_and_exits_1(
    root: Root, offline: FakeUpstream
) -> None:
    publish(offline, SCHEDULES, "nba_schedule_2026.parquet", GAMES)
    publish(offline, TEAM_BOX, "team_boxscores_2026.parquet", TEAM_BOX_ROWS)
    offline.fail_next(f"{datasets.BY_NAME[TEAM_BOX].fetch.url_prefix}team_boxscores_2026.parquet")

    result = cli(root, "setup", SCHEDULES, TEAM_BOX)

    assert result.exit_code == 1
    assert lines(result.stderr)[-1] == SETUP_RESUMES
    assert not table_exists(lake.connect(root, read_only=True), "nba", "games")
    rerun = lines(ok(cli(root, "setup", SCHEDULES, TEAM_BOX)))
    assert "captured 1 new units, 1 up to date" in rerun


def test_vacuum_merges_the_meta_files_and_records_the_run(root: Root) -> None:
    con = lake.connect(root)
    for _ in range(3):
        con.execute("INSERT INTO lake.meta.runs VALUES ('x', 'probe', now(), now(), true, '')")
    con.close()

    out = ok(cli(root, "vacuum"))

    assert lines(out)[0] == (
        "vacuum: rewrote 0 and merged 3 files, expired 0 snapshots, deleted 0 files"
    )
    assert lines(out)[1].startswith("vacuum: live files ")
    assert query(root, "SELECT command, ok FROM meta.runs WHERE command = 'vacuum'") == [
        ("vacuum", True)
    ]


def test_a_second_curate_with_nothing_new_staged_builds_nothing_and_says_so(
    root: Root, offline: FakeUpstream
) -> None:
    publish(offline, SCHEDULES, "nba_schedule_2026.parquet", GAMES)
    publish(offline, TEAM_BOX, "team_boxscores_2026.parquet", TEAM_BOX_ROWS)
    ok(cli(root, "refresh", SCHEDULES, TEAM_BOX))

    out = lines(ok(cli(root, "curate")))
    forced = lines(ok(cli(root, "curate", "--rebuild")))

    assert "unchanged: 1 models" in out and not any(x.startswith("nba.") for x in out)
    assert f"nba.games: {len(GAMES)} rows" in forced


def test_refresh_with_a_failed_download_still_curates_then_exits_1_and_records_it(
    root: Root, offline: FakeUpstream
) -> None:
    publish(offline, SCHEDULES, "nba_schedule_2026.parquet", GAMES)
    publish(offline, TEAM_BOX, "team_boxscores_2026.parquet", TEAM_BOX_ROWS)
    ok(cli(root, "refresh", SCHEDULES, TEAM_BOX))
    publish(
        offline,
        TEAM_BOX,
        "team_boxscores_2026.parquet",
        TEAM_BOX_ROWS,
        updated_at="2026-10-02T00:00:00Z",
    )
    url = f"{datasets.BY_NAME[TEAM_BOX].fetch.url_prefix}team_boxscores_2026.parquet"
    offline.fail_next(url)

    result = cli(root, "refresh", SCHEDULES, TEAM_BOX)

    assert result.exit_code == 1
    assert result.stderr.startswith(f"failed {url}: ReadError")
    assert "unchanged: 1 models" in lines(result.stdout)
    assert any(line.startswith("vacuum: ") for line in lines(result.stdout))
    runs = query(root, "SELECT ok, detail FROM meta.runs WHERE command = 'refresh' ORDER BY ALL")
    assert runs == [(False, "UnitsFailed: capture failed 1 units"), (True, "")]


def test_a_unit_that_fails_to_stage_fails_the_run_after_the_rest_is_staged(
    root: Root, offline: FakeUpstream
) -> None:
    publish(offline, SCHEDULES, "nba_schedule_2026.parquet", GAMES)
    publish(offline, TEAM_BOX, "team_boxscores_2026.parquet", TEAM_BOX_ROWS)
    fetch = datasets.BY_NAME[PBP].fetch
    assert isinstance(fetch, ReleaseAssets)
    offline.add_release_asset(fetch.repo, fetch.tag, "play_by_play_2026.parquet", b"not parquet")

    result = cli(root, "refresh", SCHEDULES, TEAM_BOX, PBP)

    assert result.exit_code == 1
    assert f"nba.games: {len(GAMES)} rows" in lines(result.stdout)
    assert result.stderr.startswith(f"failed {PBP}: 1 units, e.g. ")
    ((ok_, detail),) = query(root, "SELECT ok, detail FROM meta.runs WHERE command = 'refresh'")
    assert (ok_, detail) == (False, f"UnitsFailed: stage failed 1 units in {PBP}")
    assert cli(root, "stage", PBP).exit_code == 1
    assert query(root, "SELECT ok, detail FROM meta.runs WHERE command = 'stage'") == [
        (False, f"UnitsFailed: stage failed 1 units in {PBP}")
    ]


def test_curate_keeps_the_previous_snapshot_when_a_gate_fails(
    root: Root, offline: FakeUpstream
) -> None:
    publish(offline, SCHEDULES, "nba_schedule_2026.parquet", GAMES)
    publish(offline, TEAM_BOX, "team_boxscores_2026.parquet", TEAM_BOX_ROWS)
    ok(cli(root, "refresh", SCHEDULES, TEAM_BOX))
    published = query(root, "SELECT * FROM nba.games ORDER BY game_id")
    publish(
        offline,
        TEAM_BOX,
        "team_boxscores_2026.parquet",
        team_box_rows(GAMES, home_pts_error=1),
        updated_at="2026-10-02T00:00:00Z",
    )
    ok(cli(root, "capture", TEAM_BOX))
    ok(cli(root, "stage", TEAM_BOX))

    result = cli(root, "curate")

    assert result.exit_code == 1
    printed = lines(result.stdout)
    assert printed[:2] == [
        "gate games_game_id_unique: pass",
        "gate games_scores_agree_with_team_box: FAIL 2 violations",
    ]
    assert printed[2].startswith("  e.g. {") and len(printed) == 3
    assert result.stderr.splitlines() == [
        "quality gates failed: games_scores_agree_with_team_box (2 violations); "
        "the previous snapshot stays published"
    ]
    assert query(root, "SELECT * FROM nba.games ORDER BY game_id") == published
    assert query(root, "SELECT command, ok FROM meta.runs ORDER BY started_at") == [
        ("refresh", True),
        ("stage", True),
        ("curate", False),
    ]
    assert query(
        root,
        "SELECT violations FROM meta.gate_results "
        "WHERE gate = 'games_scores_agree_with_team_box' ORDER BY checked_at",
    ) == [(0,), (2,)]


@pytest.mark.parametrize("command", WRITE_COMMANDS)
def test_a_write_command_exits_75_and_records_nothing_while_another_holds_the_writer_lock(
    root: Root, offline: FakeUpstream, command: str
) -> None:
    lake.connect(root).close()

    with lake.writer_lock(root, "refresh"):
        result = cli(root, command)

    assert result.exit_code == 75, (result.stdout, result.stderr)
    assert "another nbalake write is running" in result.stderr
    assert query(root, "SELECT count(*) FROM meta.runs") == [(0,)]


@pytest.mark.parametrize("args", [("status",), ("sql", "select 1")], ids=["status", "sql"])
def test_a_read_command_runs_while_a_write_holds_the_lock(
    root: Root, args: tuple[str, ...]
) -> None:
    lake.connect(root).close()

    with lake.writer_lock(root, "refresh"):
        ok(cli(root, *args))


def test_command_set_matches_the_documented_commands() -> None:
    group = get_command(app)
    assert isinstance(group, TyperGroup)
    assert set(group.commands) == set(COMMANDS)


@pytest.mark.parametrize("command", [(), *((c,) for c in COMMANDS)], ids=["app", *COMMANDS])
def test_help_exits_0(command: tuple[str, ...]) -> None:
    """GitHub Actions makes rich color the help, which splits option names with escape codes."""
    result = runner.invoke(app, [*command, "--help"])
    text = ANSI.sub("", result.stdout)

    assert result.exit_code == 0, result.output
    assert "Usage:" in text
    assert "--root" in text or command in {(), *((c,) for c in LAKELESS_COMMANDS)}
