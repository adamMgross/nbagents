from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

CURATED = "nba"


class Kind(Enum):
    TABLE = "table"
    VIEW = "view"
    SEED = "seed"


@dataclass(frozen=True, slots=True)
class Chunk:
    """A table built one value of column at a time, the values read from source.

    Invariant: a chunk's rows depend only on input rows with the same chunk value, in every
    input that has the column, so a changed input rebuilds only its chunks."""

    column: str
    source: str


@dataclass(frozen=True, slots=True)
class Model:
    name: str
    kind: Kind = Kind.TABLE
    grain: tuple[str, ...] = ()
    partition: str | None = None
    sort: tuple[str, ...] = ()
    chunk: Chunk | None = None
    description: str = ""

    @property
    def qualified(self) -> str:
        return f'lake."{CURATED}"."{self.name}"'
