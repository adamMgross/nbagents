from __future__ import annotations

import _thread
import contextlib
import io
import re
import resource
import threading
import traceback
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import duckdb

from nbalake import lake
from nbalake.explore.query import QueryTimeout
from nbalake.explore.session import OVER_CAP

MAX_OUTPUT = 20_000
PYTHON_MEMORY = "4GB"
PROC_STATUS = Path("/proc/self/status")
SIZE = re.compile(r"\s*(\d+(?:\.\d+)?)\s*([KMGT]i?B|B)?\s*", re.IGNORECASE)
UNITS = {
    "B": 1,
    **{f"{u}B": 1000 ** (i + 1) for i, u in enumerate("KMGT")},
    **{f"{u}IB": 1024 ** (i + 1) for i, u in enumerate("KMGT")},
}


@dataclass(frozen=True, slots=True)
class ScriptResult:
    output: str
    truncated: bool
    error: str | None


class ScriptError(Exception):
    pass


def _script_traceback(e: BaseException, filename: str) -> str:
    frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == filename]
    lines = traceback.format_list(frames) + traceback.format_exception_only(e)
    return "".join(lines).rstrip()


def size_bytes(text: str) -> int:
    m = SIZE.fullmatch(text)
    if m is None:
        raise ValueError(f"not a size like 4GB: {text!r}")
    return int(float(m[1]) * UNITS[(m[2] or "B").upper()])


def _data_segment() -> int:
    for line in PROC_STATUS.read_text().splitlines():
        if line.startswith("VmData:"):
            return int(line.split()[1]) * 1024
    raise OSError(f"{PROC_STATUS} has no VmData line")


@contextlib.contextmanager
def data_limit(extra: int) -> Generator[None]:
    """Caps the process's data segment at its current size plus extra while the block runs.

    Linux only: macOS has no /proc to measure the segment, so there the block runs uncapped.
    """
    if not PROC_STATUS.exists():
        yield
        return
    soft, hard = resource.getrlimit(resource.RLIMIT_DATA)
    cap = _data_segment() + extra
    resource.setrlimit(
        resource.RLIMIT_DATA, (cap if hard == resource.RLIM_INFINITY else min(cap, hard), hard)
    )
    try:
        yield
    finally:
        resource.setrlimit(resource.RLIMIT_DATA, (soft, hard))


def run(
    con: duckdb.DuckDBPyConnection,
    source: str,
    filename: str,
    *,
    timeout: float,
    max_output: int = MAX_OUTPUT,
) -> ScriptResult:
    import polars as pl

    pl.Config.set_tbl_rows(20)
    pl.Config.set_tbl_cols(20)
    pl.Config.set_fmt_str_lengths(80)
    namespace = {"__name__": "__main__", "con": con, "pl": pl, "duckdb": duckdb}
    out = io.StringIO()
    error = None
    code = compile(source, filename, "exec")
    fired = threading.Event()

    def stop() -> None:
        fired.set()
        con.interrupt()
        _thread.interrupt_main()

    timer = threading.Timer(timeout, stop)
    timer.start()
    extra = size_bytes(lake.CAPS.memory) + size_bytes(PYTHON_MEMORY)
    try:
        try:
            with data_limit(extra), contextlib.redirect_stdout(out):
                exec(code, namespace)
        finally:
            timer.cancel()
            timer.join()
    except BaseException as e:
        if fired.is_set():
            error = str(QueryTimeout(timeout))
        elif isinstance(e, duckdb.OutOfMemoryException | MemoryError):
            error = OVER_CAP
        elif isinstance(e, Exception):
            error = _script_traceback(e, filename)
        else:
            raise
    text = out.getvalue()
    truncated = len(text) > max_output
    return ScriptResult(text[:max_output], truncated, error)
