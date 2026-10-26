from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nbalake.cli import app
from nbalake.explore import skills
from nbalake.explore.skills import Skill
from nbalake.runtime import Runtime, Target, adapt

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
APP_SKILLS = ("nba-lake", "nba-lake-setup", "report")


def tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def doc_paths(text: str, prefix: str) -> set[str]:
    return set(re.findall(re.escape(prefix) + r"[A-Za-z0-9_./-]*[A-Za-z0-9_]", text))


def test_adapt_keeps_the_target_runtimes_blocks_and_drops_the_markers() -> None:
    text = "a\n<!-- repo -->\nrepo only\n<!-- end -->\n<!-- app -->\napp only\n<!-- end -->\nz\n"

    assert adapt(text, Target(Runtime.REPO, "docs/")) == "a\nrepo only\nz\n"
    assert adapt(text, Target(Runtime.APP, "/h/docs/")) == "a\napp only\nz\n"


def test_adapt_for_the_app_drops_uv_run_and_points_backticked_docs_at_the_installed_copy() -> None:
    text = "run `uv run nba sql`, read `docs/reports.md`, see https://docs/x\n"

    out = adapt(text, Target(Runtime.APP, "/h/.claude/skills/nba-lake/docs/"))

    assert out == (
        "run `nba sql`, read `/h/.claude/skills/nba-lake/docs/reports.md`, see https://docs/x\n"
    )


@pytest.mark.parametrize(
    "text",
    [
        "<!-- repo -->\nno end\n",
        "<!-- end -->\n",
        "<!-- repo -->\n<!-- app -->\n<!-- end -->\n<!-- end -->\n",
    ],
)
def test_adapt_rejects_unbalanced_or_nested_blocks(text: str) -> None:
    with pytest.raises(ValueError, match="block"):
        adapt(text, Target(Runtime.REPO, "docs/"))


@pytest.mark.parametrize("skill", list(Skill))
def test_repo_skill_files_are_the_repo_render(skill: Skill) -> None:
    path = REPO / ".claude" / "skills" / skill.value / "SKILL.md"

    assert path.read_text(encoding="utf-8") == skills.render(skill, skills.target(Runtime.REPO)), (
        "regenerate with: uv run nbalake install-skills"
    )


def test_install_for_the_app_writes_three_skills_and_the_docs_they_read(tmp_path: Path) -> None:
    dest = tmp_path / "home" / ".claude" / "skills"

    skills.install(dest, Runtime.APP, DOCS)

    assert sorted(p.name for p in dest.iterdir()) == sorted(APP_SKILLS)
    prefix = f"{dest / 'nba-lake' / 'docs'}/"
    named: set[str] = set()
    for name in APP_SKILLS:
        text = (dest / name / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith(f"---\nname: {name}\n")
        assert "uv run" not in text
        assert "uv sync" not in text
        assert "`docs/" not in text
        assert "src/nbalake" not in text
        named |= doc_paths(text, prefix)
    assert f"{prefix}basketball/README.md" in named
    assert f"{prefix}reports.md" in named
    missing = sorted(p for p in named if not Path(p).exists())
    assert missing == []


def test_install_for_the_app_twice_is_byte_identical_and_drops_a_stale_doc(
    tmp_path: Path,
) -> None:
    dest = tmp_path / "skills"
    skills.install(dest, Runtime.APP, DOCS)
    first = tree(dest)
    stale = dest / "nba-lake" / "docs" / "basketball" / "retired.md"
    stale.write_text("old")

    skills.install(dest, Runtime.APP, DOCS)

    assert tree(dest) == first


def test_install_for_the_repo_writes_only_the_skill_files(tmp_path: Path) -> None:
    skills.install(tmp_path, Runtime.REPO, DOCS)

    assert sorted(tree(tmp_path)) == sorted(f"{name}/SKILL.md" for name in APP_SKILLS)


def test_install_skills_command_writes_where_it_is_told(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["install-skills", "--dest", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert str(tmp_path) in result.output
    assert (tmp_path / "nba-lake" / "SKILL.md").exists()


def test_app_setup_skill_builds_with_the_installed_commands() -> None:
    text = skills.render(Skill.SETUP, skills.target(Runtime.APP, Path("/h/.claude/skills")))

    assert "caffeinate -i nbalake setup" in text
    assert "~/.local/bin/nbalake" in text
    assert "`git`" not in text
    assert "clone" not in text
