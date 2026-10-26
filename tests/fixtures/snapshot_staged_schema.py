import json
import sys
from pathlib import Path

import nbalake

SKIP = ("nba", "meta")


def main(out: Path) -> None:
    con = nbalake.connect(nbalake.Root.resolve(), read_only=True)
    rows = con.execute(
        "SELECT table_schema, table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_catalog = 'lake' ORDER BY table_schema, table_name, ordinal_position"
    ).fetchall()
    tables: dict[str, list[list[str]]] = {}
    for schema, table, column, kind in rows:
        if schema not in SKIP:
            tables.setdefault(f"{schema}.{table}", []).append([column, kind])
    lines = [f"{json.dumps(t)}: {json.dumps(cols)}" for t, cols in sorted(tables.items())]
    out.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("staged_schema.json"))
