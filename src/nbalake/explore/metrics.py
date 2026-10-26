from __future__ import annotations

from dataclasses import dataclass

from nbalake.explore import macros

FIELDS = ("name", "version", "summary")


@dataclass(frozen=True, slots=True)
class Metric:
    name: str
    version: int
    summary: str
    methodology: str
    macros: tuple[macros.Macro, ...]


def registered() -> tuple[Metric, ...]:
    """Every metric under src/nbalake/metrics, by name, with its macros in load order."""
    shipped = macros.shipped()
    found: list[Metric] = []
    for folder in macros.metric_folders():
        header, methodology = _front_matter((folder / "README.md").read_text(encoding="utf-8"))
        if header.get("name") != folder.name:
            raise ValueError(f"metric {folder.name}: README name is {header.get('name')!r}")
        own = tuple(m for m in shipped if m.metric == folder.name)
        if not own:
            raise ValueError(f"metric {folder.name}: no macro .sql file beside its README")
        found.append(
            Metric(folder.name, int(header["version"]), header["summary"], methodology, own)
        )
    return tuple(found)


def _front_matter(text: str) -> tuple[dict[str, str], str]:
    head, sep, body = text.removeprefix("---\n").partition("\n---\n")
    if not text.startswith("---\n") or not sep:
        raise ValueError("a metric README starts with a --- front matter block")
    header = dict(line.split(": ", 1) for line in head.splitlines() if line)
    missing = [f for f in FIELDS if f not in header]
    if missing:
        raise ValueError(f"metric README front matter lacks {', '.join(missing)}")
    return header, body.lstrip("\n")
