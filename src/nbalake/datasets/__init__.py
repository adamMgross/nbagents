from __future__ import annotations

from fnmatch import fnmatchcase

from nbalake.datasets import bref, fivethirtyeight, l2m, odds, sdv, shufinskiy, site_data
from nbalake.model import Dataset

ALL: tuple[Dataset, ...] = (
    *sdv.DATASETS,
    *shufinskiy.DATASETS,
    *site_data.DATASETS,
    *fivethirtyeight.DATASETS,
    *l2m.DATASETS,
    *bref.DATASETS,
    *odds.DATASETS,
)

BY_NAME: dict[str, Dataset] = {d.name: d for d in ALL}
if len(BY_NAME) != len(ALL):
    dupes = sorted({d.name for d in ALL if sum(x.name == d.name for x in ALL) > 1})
    raise RuntimeError(f"duplicate dataset names: {dupes}")

SCHEMAS: tuple[str, ...] = tuple(sorted({d.schema for d in ALL}))


def select(patterns: list[str] | tuple[str, ...]) -> list[Dataset]:
    """Datasets whose name equals, starts with '<pattern>.', or glob-matches a pattern."""
    if not patterns:
        return list(ALL)
    chosen: dict[str, Dataset] = {}
    for p in patterns:
        hits = [d for d in ALL if d.name == p or d.schema == p or fnmatchcase(d.name, p)]
        if not hits:
            raise KeyError(f"no dataset matches {p!r}")
        chosen.update({d.name: d for d in hits})
    return [d for d in ALL if d.name in chosen]
