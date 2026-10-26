"""Checks a machine can hold the lake before the first build starts."""

from __future__ import annotations

import shutil
from pathlib import Path

REQUIRED_BYTES = 50 * 2**30
PLATFORMS = ("linux", "darwin")
GB = 2**30


def problems(platform: str, free: int, built: int, root: Path) -> list[str]:
    found: list[str] = []
    if platform not in PLATFORMS:
        found.append(
            f"nbalake runs on Linux and macOS, not {platform}. On Windows, run it inside WSL."
        )
    if free + built < REQUIRED_BYTES:
        found.append(
            f"the lake needs {REQUIRED_BYTES / GB:.0f} GB at {root}, and {free / GB:.0f} GB is "
            f"free with {built / GB:.0f} GB already built. Free space, or set NBALAKE_ROOT to a "
            "directory on a bigger drive."
        )
    return found


def free_bytes(path: Path) -> int:
    while not path.exists():
        path = path.parent
    return shutil.disk_usage(path).free


def lake_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
