from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb

from nbalake.lake import CURATE_COMMIT, METADATA

DELETE_AFTER = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class CatalogSize:
    live_files: int
    stats_rows: int
    snapshots: int


@dataclass(frozen=True, slots=True)
class VacuumReport:
    before: CatalogSize
    after: CatalogSize
    rewritten: int
    merged: int
    expired: int
    deleted: int


def catalog_size(con: duckdb.DuckDBPyConnection) -> CatalogSize:
    row = con.execute(
        f"SELECT (SELECT count(*) FROM {METADATA}.ducklake_data_file WHERE end_snapshot IS NULL), "
        f"(SELECT count(*) FROM {METADATA}.ducklake_file_column_stats), "
        f"(SELECT count(*) FROM {METADATA}.ducklake_snapshot)"
    ).fetchall()[0]
    return CatalogSize(*(int(n) for n in row))


def previous_curate(con: duckdb.DuckDBPyConnection) -> int | None:
    rows = con.execute(
        "SELECT snapshot_id FROM ducklake_snapshots('lake') WHERE commit_message = ? "
        "ORDER BY snapshot_id DESC LIMIT 2",
        [CURATE_COMMIT],
    ).fetchall()
    return int(rows[1][0]) if len(rows) == 2 else None


def _files_processed(rows: list[tuple[Any, ...]]) -> int:
    return sum(int(r[2]) for r in rows)


def mergeable(con: duckdb.DuckDBPyConnection) -> list[tuple[str, str]]:
    """Tables with two or more live files under the target size, merged one at a time so
    peak memory is one table's merge."""
    rows = con.execute(
        f"SELECT s.schema_name, t.table_name FROM {METADATA}.ducklake_data_file f "
        f"JOIN {METADATA}.ducklake_table t USING (table_id) "
        f"JOIN {METADATA}.ducklake_schema s USING (schema_id) "
        "WHERE f.end_snapshot IS NULL AND t.end_snapshot IS NULL AND s.end_snapshot IS NULL "
        "AND f.file_size_bytes < (SELECT value::BIGINT FROM ducklake_options('lake') "
        "WHERE option_name = 'target_file_size') "
        "GROUP BY ALL HAVING count(*) > 1 ORDER BY ALL"
    ).fetchall()
    return [(schema, table) for schema, table in rows]


def expire_before(con: duckdb.DuckDBPyConnection, snapshot_id: int) -> int:
    rows = con.execute(
        "SELECT snapshot_id FROM ducklake_snapshots('lake') WHERE snapshot_id < ?", [snapshot_id]
    ).fetchall()
    if not rows:
        return 0
    versions = [int(r[0]) for r in rows]
    con.execute("CALL ducklake_expire_snapshots('lake', versions => ?)", [versions]).fetchall()
    return len(versions)


def vacuum(con: duckdb.DuckDBPyConnection, *, now: datetime | None = None) -> VacuumReport:
    before = catalog_size(con)
    rewritten = _files_processed(con.execute("CALL ducklake_rewrite_data_files('lake')").fetchall())
    merged = sum(
        _files_processed(
            con.execute(
                "CALL ducklake_merge_adjacent_files('lake', ?, schema => ?)", [table, schema]
            ).fetchall()
        )
        for schema, table in mergeable(con)
    )
    floor = previous_curate(con)
    expired = 0 if floor is None else expire_before(con, floor)
    cutoff = (now or datetime.now(UTC)) - DELETE_AFTER
    deleted = len(
        con.execute("CALL ducklake_cleanup_old_files('lake', older_than => ?)", [cutoff]).fetchall()
    ) + len(
        con.execute(
            "CALL ducklake_delete_orphaned_files('lake', older_than => ?)", [cutoff]
        ).fetchall()
    )
    return VacuumReport(before, catalog_size(con), rewritten, merged, expired, deleted)
