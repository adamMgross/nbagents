from __future__ import annotations

import shutil
from enum import Enum
from importlib import resources
from pathlib import Path

from nbalake.explore.guide import FRONTMATTER, render_guide
from nbalake.runtime import Runtime, Target, adapt

DOCS = ("basketball", "reports.md", "metrics.md", "data-dictionary.md", "dataset-guide.md")


class Skill(Enum):
    NBA_LAKE = "nba-lake"
    SETUP = "nba-lake-setup"
    REPORT = "report"


TEMPLATES = {Skill.SETUP: "setup.md", Skill.REPORT: "report.md"}


def default_dest(runtime: Runtime) -> Path:
    if runtime is Runtime.APP:
        return Path.home() / ".claude" / "skills"
    return runtime.files / ".claude" / "skills"


def target(runtime: Runtime, dest: Path | None = None) -> Target:
    if runtime is Runtime.REPO:
        return Target(runtime, "docs/")
    return Target(runtime, f"{(dest or default_dest(runtime)) / Skill.NBA_LAKE.value / 'docs'}/")


def render(skill: Skill, target: Target) -> str:
    match skill:
        case Skill.NBA_LAKE:
            return FRONTMATTER + render_guide(target)
        case Skill.SETUP | Skill.REPORT:
            template = resources.files("nbalake.explore") / TEMPLATES[skill]
            return adapt(template.read_text(encoding="utf-8"), target)


def install(dest: Path, runtime: Runtime, docs: Path) -> None:
    """Write every skill under dest, and for the app a copy of the docs they name."""
    rendered = target(runtime, dest)
    for skill in Skill:
        path = dest / skill.value / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(skill, rendered), encoding="utf-8")
    if runtime is Runtime.APP:
        copy = dest / Skill.NBA_LAKE.value / "docs"
        shutil.rmtree(copy, ignore_errors=True)
        copy.mkdir()
        for name in DOCS:
            if (docs / name).is_dir():
                shutil.copytree(docs / name, copy / name)
            else:
                shutil.copyfile(docs / name, copy / name)
