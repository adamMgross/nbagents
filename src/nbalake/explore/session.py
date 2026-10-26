from __future__ import annotations

import time

import duckdb

from nbalake import lake
from nbalake.explore import macros

SCRATCH = "scratch"
PROVENANCE = "__provenance"
LOCK_WAIT_SECONDS = 10.0
OVER_CAP = (
    f"the query passed the {lake.CAPS.memory} memory cap or the spill cap. Narrow it to a "
    "season, game, or player, or use a macro or rollup. A larger spill needs the owner's "
    "agreement to a size, then --allow-spill SIZE."
)


def connect(
    root: lake.Root, *, scratch: bool = False, allow_spill: str | None = None
) -> duckdb.DuckDBPyConnection:
    limits = lake.CAPS if allow_spill is None else lake.Limits(lake.CAPS.memory, allow_spill)
    con = lake.connect(root, read_only=True, limits=limits)
    con.execute("SET enable_progress_bar = false")
    macros.load(con)
    if scratch:
        attach_scratch(con, root)
    return con


def attach_scratch(con: duckdb.DuckDBPyConnection, root: lake.Root) -> None:
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            con.execute(f"ATTACH '{root.scratch}' AS {SCRATCH}")
            return
        except duckdb.IOException as e:
            if "lock" not in str(e).lower() or time.monotonic() > deadline:
                raise
            time.sleep(0.2)


def needs_scratch(sql: str) -> bool:
    return SCRATCH in sql.lower()
