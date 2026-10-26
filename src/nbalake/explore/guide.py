from __future__ import annotations

from importlib import resources

from nbalake.explore import macros, metrics
from nbalake.explore.catalog import caveats
from nbalake.runtime import Target, adapt

DESCRIPTION = (
    "Answer questions about NBA and BAA games, players, teams, box scores, play-by-play, "
    "shots, lineups, tracking, awards, betting lines, and Last Two Minute reports from the "
    "local NBA lake with the read-only nba CLI. Use for any basketball stats question, "
    "lookup, comparison, or analysis."
)
FRONTMATTER = f"---\nname: nba-lake\ndescription: {DESCRIPTION}\n---\n\n"


def render_guide(target: Target) -> str:
    template = adapt(
        (resources.files("nbalake.explore") / "guide.md").read_text(encoding="utf-8"), target
    )
    notes = "\n".join(f"- `{c.subject}` ({c.seasons}): {c.note}" for c in caveats())
    listing = "\n".join(
        f"- `{m.signature}`: {m.description}" for m in macros.shipped() if m.metric is None
    )
    registered = "\n".join(
        f"- `{x.name}` (version {x.version}): {x.summary} "
        + ", ".join(f"`{m.name}`" for m in x.macros)
        for x in metrics.registered()
    )
    return (
        template.replace("<!-- caveats -->", notes)
        .replace("<!-- macros -->", listing)
        .replace("<!-- metrics -->", registered)
    )
