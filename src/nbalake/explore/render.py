from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import cast

from rich.console import Console
from rich.table import Table

CELL_WIDTH = 80


class Format(Enum):
    MD = "md"
    JSONL = "jsonl"
    CSV = "csv"
    TABLE = "table"


def cell(value: object, *, raw: bool = False) -> str:
    match value:
        case None:
            return "NULL"
        case bool():
            return "true" if value else "false"
        case float() if not raw:
            return f"{value:.3f}"
        case datetime() | date():
            return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
        case _:
            text = str(value)
    if not raw and len(text) > CELL_WIDTH:
        return text[: CELL_WIDTH - 3] + "..."
    return text


def _json_value(value: object) -> object:
    match value:
        case Decimal():
            return float(value)
        case datetime() | date():
            return value.isoformat()
        case list() | tuple():
            return [_json_value(v) for v in cast(Iterable[object], value)]
        case dict():
            items = cast(dict[object, object], value).items()
            return {str(k): _json_value(v) for k, v in items}
        case int() if abs(value) > 2**53:
            return str(value)
        case _:
            return (
                value
                if value is None or isinstance(value, str | int | float | bool)
                else str(value)
            )


def _md_cell(value: object, raw: bool) -> str:
    return cell(value, raw=raw).replace("|", "\\|").replace("\n", " ")


def render(
    columns: Sequence[str], rows: Sequence[Sequence[object]], fmt: Format, *, raw: bool = False
) -> str:
    match fmt:
        case Format.MD:
            out = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
            out += ["| " + " | ".join(_md_cell(v, raw) for v in row) + " |" for row in rows]
            return "\n".join(out)
        case Format.JSONL:
            return "\n".join(
                json.dumps({c: _json_value(v) for c, v in zip(columns, row, strict=True)})
                for row in rows
            )
        case Format.CSV:
            buf = io.StringIO()
            writer = csv.writer(buf, lineterminator="\n")
            writer.writerow(columns)
            writer.writerows(["" if v is None else _json_value(v) for v in row] for row in rows)
            return buf.getvalue().rstrip("\n")
        case Format.TABLE:
            table = Table(*columns)
            for row in rows:
                table.add_row(*(cell(v, raw=raw) for v in row))
            console = Console(file=io.StringIO(), width=200, record=True)
            console.print(table)
            return console.export_text().rstrip("\n")
