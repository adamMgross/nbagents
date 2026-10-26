"""Smoke tests of the frozen app, run with NBALAKE_APP set to a built dist/nbalake directory."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import duckdb
import pytest

from nbalake.curate import shipped_steps
from nbalake.explore.skills import DOCS
from nbalake.lake import Root
from nbalake.profile import write_catalog
from nbalake.runtime import EXTENSIONS
from tests.curated import build_models, empty_lake, insert, models, sources

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / "src" / "nbalake"
MODELS = ("franchises", "team_seasons", "teams", "games")

pytestmark = pytest.mark.skipif(
    not os.environ.get("NBALAKE_APP"), reason="set NBALAKE_APP to a built app directory"
)


@pytest.fixture(scope="module")
def app() -> Path:
    return Path(os.environ["NBALAKE_APP"]).resolve()


@pytest.fixture(scope="module")
def lake(tmp_path_factory: pytest.TempPathFactory) -> Root:
    root = Root(tmp_path_factory.mktemp("bundle") / "lake")
    con = empty_lake(root, sources(*MODELS))
    build_models(con, *MODELS)
    insert(
        con,
        "nba.games",
        [
            {
                "game_id": "0041500407",
                "season": 2016,
                "game_date": "2016-06-19",
                "season_type": "playoffs",
                "home_team_id": 1610612744,
                "away_team_id": 1610612739,
                "home_pts": 89,
                "away_pts": 93,
            }
        ],
    )
    write_catalog(con, {s.model.name: s.sql for s in shipped_steps(models(*MODELS))})
    con.close()
    return root


def run(app: Path, home: Path, command: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run through a symlink outside the bundle, as the installer's ~/.local/bin links do."""
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    link = bin_dir / command
    if not link.exists():
        link.symlink_to(app / command)
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"}
    return subprocess.run(
        [str(link), *args], capture_output=True, text=True, env=env, timeout=120, check=False
    )


def ok(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, (result.stdout, result.stderr)
    return result.stdout


def test_bundle_holds_every_package_data_file_the_docs_and_the_extensions(app: Path) -> None:
    internal = app / "_internal"
    data = [
        p.relative_to(PACKAGE.parent)
        for p in PACKAGE.rglob("*")
        if p.is_file() and p.suffix not in {".py", ".pyc"} and "__pycache__" not in p.parts
    ]
    assert data

    missing = [str(p) for p in data if not (internal / p).is_file()]
    missing += [f"docs/{d}" for d in DOCS if not (internal / "docs" / d).exists()]
    for name in ("ducklake", "sqlite_scanner"):
        found = list((internal / EXTENSIONS / f"v{duckdb.__version__}").glob(f"*/{name}.*"))
        missing += [] if found else [name]

    assert missing == []


def test_nbalake_lists_the_datasets_without_a_lake(app: Path, tmp_path: Path) -> None:
    out = ok(run(app, tmp_path, "nbalake", "datasets", "--root", str(tmp_path / "none")))

    assert "sdv.nba_stats_pbp" in out


def test_nba_guide_points_at_the_installed_docs(app: Path, tmp_path: Path) -> None:
    out = ok(run(app, tmp_path, "nba", "guide"))

    assert out.startswith("# NBA lake")
    assert f"`{tmp_path}/.claude/skills/nba-lake/docs/basketball/README.md`" in out
    assert "nba py" not in out


def test_nba_sql_reads_the_lake_with_only_the_bundled_extensions(
    app: Path, lake: Root, tmp_path: Path
) -> None:
    query = "select home_pts from nba.games"
    out = ok(run(app, tmp_path, "nba", "sql", query, "--root", str(lake.path)))

    assert "89" in out
    assert not (tmp_path / ".duckdb").exists()


def test_nba_report_renders_a_spec(app: Path, lake: Root, tmp_path: Path) -> None:
    spec = tmp_path / "2026-10-25-finals.json"
    spec.write_text(
        json.dumps(
            {
                "name": "Game sevens",
                "title": "Game sevens",
                "finding": "Cleveland won at Golden State.",
                "blocks": [
                    {
                        "type": "table",
                        "title": "Games",
                        "sql": "select game_id, home_pts from nba.games",
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

    out = ok(run(app, tmp_path, "nba", "report", str(spec), "--root", str(lake.path)))

    page = spec.with_suffix(".html")
    assert out.strip() == str(page)
    assert "0041500407" in page.read_text()


def test_install_skills_writes_the_skills_and_docs_into_home(app: Path, tmp_path: Path) -> None:
    ok(run(app, tmp_path, "nbalake", "install-skills"))

    skills = tmp_path / ".claude" / "skills"
    assert sorted(p.name for p in skills.iterdir()) == ["nba-lake", "nba-lake-setup", "report"]
    assert (skills / "nba-lake" / "docs" / "basketball" / "README.md").is_file()
    assert "caffeinate -i nbalake setup" in (skills / "nba-lake-setup" / "SKILL.md").read_text()
