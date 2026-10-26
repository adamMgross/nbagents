from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from nbalake.explore import macros, metrics
from nbalake.explore.cli import app
from nbalake.explore.guide import render_guide
from nbalake.explore.skills import target
from nbalake.runtime import Runtime

MACRO = """-- What it returns.
-- example: from {name}()
CREATE OR REPLACE TEMP MACRO {name}() AS TABLE SELECT 1 AS x
"""


def folder(base: Path, name: str, readme: str, *macro_names: str) -> Path:
    f = base / name
    f.mkdir()
    (f / "README.md").write_text(readme)
    for m in macro_names:
        (f / f"{m}.sql").write_text(MACRO.format(name=m))
    return f


def test_career_postseason_registers_with_its_macros_callees_first() -> None:
    found = {m.name: m for m in metrics.registered()}

    cp = found["career_postseason"]
    assert cp.version >= 1
    assert [m.name for m in cp.macros] == [
        "postseason_team_credit",
        "postseason_game_credit",
        "postseason_season_credit",
        "career_postseason",
    ]
    assert cp.methodology.startswith("# Career postseason achievement")
    assert {m.metric for m in macros.shipped() if m.name.startswith("elo_")} == {None}


@pytest.mark.parametrize(
    ("readme", "macro_names", "message"),
    [
        ("---\nname: other\nversion: 1\nsummary: s\n---\n# T\n", ("m",), "README name is 'other'"),
        ("---\nname: x\nsummary: s\n---\n# T\n", ("m",), "lacks version"),
        ("# T\n", ("m",), "starts with a --- front matter block"),
        ("---\nname: x\nversion: 1\nsummary: s\n---\n# T\n", (), "no macro .sql file"),
    ],
)
def test_a_metric_folder_that_cannot_be_read_is_rejected_by_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    readme: str,
    macro_names: tuple[str, ...],
    message: str,
) -> None:
    made = folder(tmp_path, "x", readme, *macro_names)
    monkeypatch.setattr(macros, "metric_folders", lambda: [made])

    with pytest.raises(ValueError, match=message):
        metrics.registered()


def test_nba_metrics_lists_each_metric_with_its_version_macros_and_examples() -> None:
    out = CliRunner().invoke(app, ["metrics"])
    cp = metrics.registered()[0]

    assert out.exit_code == 0
    assert f"## career_postseason, version {cp.version}" in out.stdout
    for m in cp.macros:
        assert m.signature in out.stdout
        assert m.example in out.stdout


def test_nba_metrics_with_a_name_prints_the_methodology_page() -> None:
    out = CliRunner().invoke(app, ["metrics", "career_postseason"])

    assert out.exit_code == 0
    assert out.stdout.startswith("# Career postseason achievement")
    assert "## Limits" in out.stdout
    assert "summary:" not in out.stdout


def test_nba_metrics_with_an_unknown_name_exits_1_naming_the_registered_ones() -> None:
    out = CliRunner().invoke(app, ["metrics", "clutch"])

    assert out.exit_code == 1
    assert (
        "no metric named 'clutch'. "
        "Registered: career_postseason, career_postseason_basic, era_wins, "
        "quality_wins." in out.stderr
    )


def test_the_guide_lists_metric_macros_under_their_metric_not_with_the_other_macros() -> None:
    guide = render_guide(target(Runtime.REPO))
    version = metrics.registered()[0].version

    macros_section, _, rest = guide.partition("## Metrics")
    metrics_section = rest.partition("## Conventions")[0]
    assert "career_postseason" not in macros_section.partition("## Macros")[2]
    assert f"- `career_postseason` (version {version}):" in metrics_section
    assert "`postseason_game_credit`" in metrics_section
    assert "<!--" not in guide
