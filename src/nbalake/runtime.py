from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

EXTENSIONS = "duckdb_extensions"
MARKER = re.compile(r"^<!-- (repo|app|end) -->$")


class Runtime(Enum):
    REPO = "repo"
    APP = "app"

    @staticmethod
    def current() -> Runtime:
        return Runtime.APP if getattr(sys, "frozen", False) else Runtime.REPO

    @property
    def files(self) -> Path:
        """The directory holding `docs/`: the checkout, or the frozen bundle."""
        if self is Runtime.APP:
            bundle: str = getattr(sys, "_MEIPASS")  # noqa: B009
            return Path(bundle)
        return Path(__file__).resolve().parents[2]

    def command(self, line: str) -> str:
        return line if self is Runtime.APP else f"uv run {line}"

    def duckdb_config(self) -> dict[str, str | bool | int | float | list[str]]:
        if self is Runtime.APP:
            return {"extension_directory": str(self.files / EXTENSIONS)}
        return {}


@dataclass(frozen=True, slots=True)
class Target:
    runtime: Runtime
    docs: str


def adapt(text: str, target: Target) -> str:
    """Keep the target runtime's `<!-- repo -->` or `<!-- app -->` blocks and name its paths."""
    out: list[str] = []
    block: str | None = None
    for line in text.splitlines(keepends=True):
        m = MARKER.match(line.rstrip("\n"))
        if m is None:
            if block is None or block == target.runtime.value:
                out.append(line)
        elif m[1] == "end":
            if block is None:
                raise ValueError("end marker outside a block")
            block = None
        elif block is not None:
            raise ValueError(f"{m[1]} block inside a {block} block")
        else:
            block = m[1]
    if block is not None:
        raise ValueError(f"{block} block without an end marker")
    adapted = "".join(out)
    if target.runtime is Runtime.APP:
        adapted = adapted.replace("uv run ", "").replace("`docs/", f"`{target.docs}")
    return adapted
