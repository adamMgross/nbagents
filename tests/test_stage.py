from __future__ import annotations

import random
import re
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import cast

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from nbalake import capture as capture_module
from nbalake.capture import FetchRecord, capture
from nbalake.lake import Layout, Root, columns, layout, table_exists, utcnow
from nbalake.model import Csv, Dataset, DropFolder, Versions
from nbalake.stage import Load, StageReport, UnitPlan, retire, stage, widen
from nbalake.stage import plan as stage_plan
from tests.conftest import (
    FakeUpstream,
    csv_bytes,
    dataset,
    parquet_bytes,
    tar_xz_bytes,
    zip_bytes,
)
from tests.curated import files_read

REPO = "o/r"
TAG = "tag"
LINEAGE_TYPES = {"_unit": "VARCHAR", "_sha256": "VARCHAR", "_fetched_at": "VARCHAR"}


def rows(season: int, n: int, **extra: object) -> list[dict]:
    return [{"game_id": f"{season}{i:04d}", "pts": i * 7 % 13, **extra} for i in range(1, n + 1)]


def typed_unit(values: list, typ: pa.DataType) -> bytes:
    ids = pa.array([f"g{i}" for i in range(len(values))], pa.string())
    return parquet_bytes(pa.table({"game_id": ids, "pts": pa.array(values, typ)}))


def release(
    upstream: FakeUpstream, name: str, data: bytes, updated_at: str = "2026-10-01T00:00:00Z"
) -> None:
    upstream.add_release_asset(REPO, TAG, name, data, updated_at)


def captured(root: Root, upstream: FakeUpstream, *datasets: Dataset) -> list[FetchRecord]:
    report = capture(root, datasets, client=upstream.client, index=upstream.index)
    assert report.failed == {}
    return report.fetched


def staged_units(con: duckdb.DuckDBPyConnection, ds: Dataset) -> list[tuple]:
    return con.execute(
        "SELECT unit, sha256, fetched_at, rows FROM lake.meta.staged_units "
        "WHERE dataset = ? ORDER BY unit, fetched_at, sha256",
        [ds.name],
    ).fetchall()


def table_rows(con: duckdb.DuckDBPyConnection, ds: Dataset, cols: str = "*") -> list[tuple]:
    return con.execute(f"SELECT {cols} FROM {ds.qualified} ORDER BY game_id").fetchall()


def table_files(root: Root, ds: Dataset) -> list[Path]:
    return sorted((root.data / ds.schema / ds.table).rglob("*.parquet"))


def live_files(con: duckdb.DuckDBPyConnection, ds: Dataset) -> list[str]:
    return [
        r[0]
        for r in con.execute(
            "SELECT data_file FROM ducklake_list_files('lake', ?, schema => ?)",
            [ds.table, ds.schema],
        ).fetchall()
    ]


def snapshot_count(con: duckdb.DuckDBPyConnection) -> int:
    row = con.execute("SELECT count(*) FROM lake.snapshots()").fetchone()
    assert row is not None
    return int(row[0])


class FixedClock:
    def __init__(self, *stamps: datetime) -> None:
        self._stamps = iter(stamps)

    def now(self, tz: tzinfo | None = None) -> datetime:
        return next(self._stamps)


def test_parquet_unit_lands_with_source_columns_lineage_and_unit_season(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", parquet_bytes(rows(2020, 3)))
    ds = dataset()
    (rec,) = captured(root, upstream, ds)

    report = stage(root, con, [ds])

    assert report.loaded == {"t.parts": [("part_2020.parquet", 3)]}
    assert columns(con, ds.qualified) == {
        "game_id": "VARCHAR",
        "pts": "BIGINT",
        "season": "INTEGER",
        **LINEAGE_TYPES,
    }
    assert table_rows(con, ds, "game_id, pts") == [(r["game_id"], r["pts"]) for r in rows(2020, 3)]
    assert con.execute(
        f"SELECT DISTINCT season, _unit, _sha256, _fetched_at FROM {ds.qualified}"
    ).fetchall() == [(2020, rec.key, rec.sha256, rec.fetched_at)]


def test_source_season_column_wins_over_the_unit_derived_value(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    with_season = [{**r, "season": 1999} for r in rows(2020, 3)]
    release(upstream, "part_2020.parquet", parquet_bytes(with_season))
    ds = dataset()
    captured(root, upstream, ds)

    stage(root, con, [ds])

    assert columns(con, ds.qualified)["season"] == "BIGINT"
    assert con.execute(f"SELECT DISTINCT season FROM {ds.qualified}").fetchall() == [(1999,)]


def test_dataset_types_cast_source_columns(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(
        upstream,
        "part_2020.parquet",
        parquet_bytes([{"game_id": "a", "pts": "12"}, {"game_id": "b", "pts": "7"}]),
    )
    ds = dataset(types=(("pts", "INTEGER"),))
    captured(root, upstream, ds)

    stage(root, con, [ds])

    assert columns(con, ds.qualified)["pts"] == "INTEGER"
    assert table_rows(con, ds, "game_id, pts") == [("a", 12), ("b", 7)]


def test_rows_are_written_in_sort_order_within_each_parquet_file(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    shuffled = rows(2020, 3000)
    random.Random(7).shuffle(shuffled)
    assert [r["game_id"] for r in shuffled] != sorted(r["game_id"] for r in shuffled)
    release(upstream, "part_2020.parquet", parquet_bytes(shuffled))
    ds = dataset(sort=("game_id",))
    captured(root, upstream, ds)

    stage(root, con, [ds])

    files = table_files(root, ds)
    assert files
    for f in files:
        ids = cast(list[str], pq.read_table(f, columns=["game_id"]).column("game_id").to_pylist())
        assert ids == sorted(ids)
    assert sum(pq.read_metadata(f).num_rows for f in files) == 3000


def test_season_partition_and_sort_key_filter_reads_one_file_of_three(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    for season in (2020, 2021, 2022):
        release(upstream, f"part_{season}.parquet", parquet_bytes(rows(season, 20)))
    ds = dataset(partition="season", sort=("game_id",))
    captured(root, upstream, ds)

    stage(root, con, [ds])

    table_dir = root.data / ds.schema / ds.table
    assert sorted(p.name for p in table_dir.iterdir()) == [
        "season=2020",
        "season=2021",
        "season=2022",
    ]
    assert len(table_files(root, ds)) == 3
    assert files_read(con, f"SELECT * FROM {ds.qualified}") == 3
    assert (
        files_read(
            con, f"SELECT * FROM {ds.qualified} WHERE season = 2021 AND game_id = '20210007'"
        )
        == 1
    )


def test_a_new_table_takes_the_registry_partition_and_sort_order(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", parquet_bytes(rows(2020, 3)))
    ds = dataset(partition="season", sort=("game_id", "pts"))
    captured(root, upstream, ds)

    stage(root, con, [ds])

    assert layout(con, ds.schema, ds.table) == Layout("season", ("game_id", "pts"))


def test_a_changed_sort_order_is_set_on_the_existing_table_without_restaging(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", parquet_bytes(rows(2020, 3)))
    ds = dataset(sort=("game_id",))
    captured(root, upstream, ds)
    stage(root, con, [ds])
    resorted = dataset(sort=("season", "game_id"))

    report = stage(root, con, [resorted])

    assert report.failed == {} and report.unchanged == [ds.name]
    assert layout(con, ds.schema, ds.table) == Layout(None, ("season", "game_id"))
    assert stage(root, con, [resorted]).unchanged == [ds.name]


def test_a_changed_partition_fails_the_dataset_until_a_rebuild_restages_it(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    for season in (2020, 2021):
        release(upstream, f"part_{season}.parquet", parquet_bytes(rows(season, 3)))
    ds = dataset(partition="season", sort=("game_id",))
    captured(root, upstream, ds)
    stage(root, con, [ds])
    staged = table_rows(con, ds, "game_id, pts")
    unpartitioned = dataset(sort=("season", "game_id"))

    drifted = stage(root, con, [unpartitioned])

    assert list(drifted.failed) == [ds.name]
    error = drifted.failed[ds.name]["layout"]
    assert error.startswith("LayoutDrift: ") and f"--rebuild {ds.name}" in error
    assert layout(con, ds.schema, ds.table) == Layout("season", ("game_id",))
    rebuilt = stage(root, con, [unpartitioned], rebuild=True)
    assert rebuilt.failed == {}
    assert layout(con, ds.schema, ds.table) == Layout(None, ("season", "game_id"))
    assert table_rows(con, ds, "game_id, pts") == staged
    assert live_files(con, ds) and not any("season=" in f for f in live_files(con, ds))


def test_new_column_in_a_later_unit_is_added_and_earlier_rows_read_null(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", parquet_bytes(rows(2020, 2)))
    ds = dataset()
    captured(root, upstream, ds)
    stage(root, con, [ds])

    release(upstream, "part_2021.parquet", parquet_bytes(rows(2021, 2, ast=4)))
    captured(root, upstream, ds)
    report = stage(root, con, [ds])

    assert report.loaded == {"t.parts": [("part_2021.parquet", 2)]}
    assert columns(con, ds.qualified)["ast"] == "BIGINT"
    assert table_rows(con, ds, "season, ast") == [(2020, None), (2020, None), (2021, 4), (2021, 4)]


@pytest.mark.parametrize(
    ("first_type", "second_type", "second_values", "before", "after"),
    [
        pytest.param(pa.int64(), pa.int32(), [3, 4], "BIGINT", "BIGINT", id="integer-into-bigint"),
        pytest.param(pa.int32(), pa.int64(), [3, 2**40], "INTEGER", "BIGINT", id="bigint-widens"),
        pytest.param(pa.int64(), pa.float64(), [3.5, 4.0], "BIGINT", "DOUBLE", id="double-widens"),
    ],
)
def test_numeric_columns_widen_across_units_and_keep_every_row(
    root: Root,
    con: duckdb.DuckDBPyConnection,
    upstream: FakeUpstream,
    first_type: pa.DataType,
    second_type: pa.DataType,
    second_values: list,
    before: str,
    after: str,
) -> None:
    release(upstream, "part_2020.parquet", typed_unit([1, 2], first_type))
    ds = dataset()
    captured(root, upstream, ds)
    stage(root, con, [ds])
    assert columns(con, ds.qualified)["pts"] == before

    release(upstream, "part_2021.parquet", typed_unit(second_values, second_type))
    captured(root, upstream, ds)
    report = stage(root, con, [ds])

    assert report.failed == {}
    assert columns(con, ds.qualified)["pts"] == after
    pts = con.execute(f"SELECT pts FROM {ds.qualified} ORDER BY season, game_id").fetchall()
    assert [p for (p,) in pts] == [1, 2, *second_values]


def test_numeric_unit_into_varchar_column_is_absorbed_as_text(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", typed_unit(["12", "7"], pa.string()))
    ds = dataset()
    captured(root, upstream, ds)
    stage(root, con, [ds])

    release(upstream, "part_2021.parquet", typed_unit([3, 2**40], pa.int64()))
    captured(root, upstream, ds)
    report = stage(root, con, [ds])

    assert report.failed == {}
    assert columns(con, ds.qualified)["pts"] == "VARCHAR"
    pts = con.execute(f"SELECT pts FROM {ds.qualified} ORDER BY season, game_id").fetchall()
    assert [p for (p,) in pts] == ["12", "7", "3", str(2**40)]


def test_varchar_unit_into_bigint_column_reports_schema_drift_and_rolls_back(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", parquet_bytes(rows(2020, 3)))
    ds = dataset()
    captured(root, upstream, ds)
    stage(root, con, [ds])
    cols_before = columns(con, ds.qualified)
    rows_before = table_rows(con, ds)
    units_before = staged_units(con, ds)
    snapshots_before = snapshot_count(con)

    # extra precedes pts in the unit, so its ADD COLUMN runs before the drift aborts the
    # transaction and must be rolled back with it.
    drifting = parquet_bytes([{"game_id": "x", "extra": 1, "pts": "twelve"}])
    release(upstream, "part_2021.parquet", drifting)
    captured(root, upstream, ds)
    report = stage(root, con, [ds])

    assert report.loaded == {}
    assert report.failed == {
        "t.parts": {
            "part_2021.parquet": (
                "SchemaDrift: t.parts.pts: table has BIGINT, incoming unit has VARCHAR"
            )
        }
    }
    assert columns(con, ds.qualified) == cols_before
    assert table_rows(con, ds) == rows_before
    assert staged_units(con, ds) == units_before
    assert snapshot_count(con) == snapshots_before


def test_recaptured_unit_replaces_its_rows_and_keeps_one_staged_units_row(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", parquet_bytes(rows(2020, 3)))
    ds = dataset()
    (old,) = captured(root, upstream, ds)
    stage(root, con, [ds])

    release(
        upstream,
        "part_2020.parquet",
        parquet_bytes(rows(2020, 5)),
        updated_at="2026-10-02T00:00:00Z",
    )
    (new,) = captured(root, upstream, ds)
    report = stage(root, con, [ds])

    assert new.sha256 != old.sha256
    assert report.dropped == {"t.parts": 1}
    assert report.loaded == {"t.parts": [("part_2020.parquet", 5)]}
    assert table_rows(con, ds, "game_id, pts, _sha256") == [
        (r["game_id"], r["pts"], new.sha256) for r in rows(2020, 5)
    ]
    assert staged_units(con, ds) == [("part_2020.parquet", new.sha256, new.fetched_at, 5)]
    assert root.blob(old.sha256).exists()
    assert len(root.fetches.read_text().splitlines()) == 2


def test_unchanged_dataset_is_reported_and_writes_no_snapshot(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", parquet_bytes(rows(2020, 3)))
    ds = dataset()
    captured(root, upstream, ds)
    stage(root, con, [ds])
    units_before = staged_units(con, ds)
    snapshots_before = snapshot_count(con)

    report = stage(root, con, [ds])

    assert report == StageReport(unchanged=["t.parts"])
    assert snapshot_count(con) == snapshots_before
    assert staged_units(con, ds) == units_before


def test_versions_all_keeps_every_capture_of_a_key(
    root: Root,
    con: duckdb.DuckDBPyConnection,
    upstream: FakeUpstream,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stamps = (datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 2, tzinfo=UTC))
    monkeypatch.setattr(capture_module, "datetime", FixedClock(*stamps))
    ds = dataset(versions=Versions.ALL)
    release(upstream, "part_2020.parquet", parquet_bytes(rows(2020, 3)))
    (first,) = captured(root, upstream, ds)
    stage(root, con, [ds])
    release(
        upstream,
        "part_2020.parquet",
        parquet_bytes(rows(2020, 4)),
        updated_at="2026-10-02T00:00:00Z",
    )
    (second,) = captured(root, upstream, ds)

    report = stage(root, con, [ds])

    assert report.dropped == {}
    assert report.loaded == {"t.parts": [("part_2020.parquet", 4)]}
    assert (first.fetched_at, second.fetched_at) == (
        "2026-10-01T00:00:00+00:00",
        "2026-10-02T00:00:00+00:00",
    )
    assert con.execute(
        f"SELECT _sha256, _fetched_at, count(*) FROM {ds.qualified} "
        "GROUP BY ALL ORDER BY _fetched_at"
    ).fetchall() == [
        (first.sha256, first.fetched_at, 3),
        (second.sha256, second.fetched_at, 4),
    ]
    assert staged_units(con, ds) == [
        ("part_2020.parquet", first.sha256, first.fetched_at, 3),
        ("part_2020.parquet", second.sha256, second.fetched_at, 4),
    ]


CSV = csv_bytes(["game_id", "pts"], [["a", 1], ["b", 2]])


@pytest.mark.parametrize(
    ("suffix", "data", "parse"),
    [
        pytest.param("csv", CSV, Csv(), id="plain"),
        pytest.param(
            "zip",
            zip_bytes({"README.txt": b"notes", "data/part.csv": CSV}),
            Csv(member="data/part.csv"),
            id="zip-named-member",
        ),
        pytest.param("tar.xz", tar_xz_bytes({"part.csv": CSV}), Csv(), id="tar-xz-single-member"),
    ],
)
def test_csv_units_load_from_plain_files_and_archives(
    root: Root,
    con: duckdb.DuckDBPyConnection,
    upstream: FakeUpstream,
    suffix: str,
    data: bytes,
    parse: Csv,
) -> None:
    release(upstream, f"part_2020.{suffix}", data)
    ds = dataset(match=rf"part_(?P<season>\d{{4}})\.{re.escape(suffix)}", parse=parse)
    captured(root, upstream, ds)

    report = stage(root, con, [ds])

    assert report.loaded == {"t.parts": [(f"part_2020.{suffix}", 2)]}
    assert columns(con, ds.qualified)["pts"] == "BIGINT"
    assert table_rows(con, ds, "game_id, pts, season") == [("a", 1, 2020), ("b", 2, 2020)]
    assert list(root.tmp.iterdir()) == [root.spill]
    assert list(root.spill.iterdir()) == []


def test_csv_nulls_turn_na_into_null_without_changing_the_column_type(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    body = csv_bytes(["game_id", "pts"], [["a", 1], ["b", "NA"], ["c", None]])
    release(upstream, "part_2020.csv", body)
    ds = dataset(match=r"part_(?P<season>\d{4})\.csv", parse=Csv(nulls=("", "NA")))
    captured(root, upstream, ds)

    stage(root, con, [ds])

    assert columns(con, ds.qualified)["pts"] == "BIGINT"
    assert table_rows(con, ds, "game_id, pts") == [("a", 1), ("b", None), ("c", None)]


def test_archive_with_two_members_and_no_member_name_fails_clearly(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.zip", zip_bytes({"a.csv": CSV, "b.csv": CSV}))
    ds = dataset(match=r"part_(?P<season>\d{4})\.zip", parse=Csv())
    (rec,) = captured(root, upstream, ds)

    report = stage(root, con, [ds])

    assert report.loaded == {}
    assert report.failed == {
        "t.parts": {
            "part_2020.zip": f"ValueError: {rec.sha256}: archive holds 2 files, name the member"
        }
    }
    assert not table_exists(con, ds.schema, ds.table)
    assert staged_units(con, ds) == []


def test_dataset_with_nothing_in_raw_is_missing_and_creates_nothing(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    ds = dataset()
    snapshots_before = snapshot_count(con)

    assert stage(root, con, [ds]) == StageReport(missing=["t.parts"])

    other = dataset(name="t.other", tag="other")
    upstream.add_release_asset(REPO, "other", "part_2020.parquet", parquet_bytes(rows(2020, 3)))
    captured(root, upstream, other)

    assert stage(root, con, [ds]) == StageReport(missing=["t.parts"])
    assert not table_exists(con, ds.schema, ds.table)
    assert staged_units(con, ds) == []
    assert snapshot_count(con) == snapshots_before


def test_a_new_version_that_fails_to_load_keeps_the_old_rows_until_a_good_one_arrives(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", parquet_bytes(rows(2020, 3)))
    ds = dataset()
    (old,) = captured(root, upstream, ds)
    stage(root, con, [ds])
    kept = table_rows(con, ds, "game_id, pts, _sha256")
    release(upstream, "part_2020.parquet", b"not parquet", updated_at="2026-10-02T00:00:00Z")
    captured(root, upstream, ds)

    broken = stage(root, con, [ds])

    assert list(broken.failed) == [ds.name] and broken.dropped == {}
    assert table_rows(con, ds, "game_id, pts, _sha256") == kept
    assert staged_units(con, ds) == [("part_2020.parquet", old.sha256, old.fetched_at, 3)]
    release(
        upstream,
        "part_2020.parquet",
        parquet_bytes(rows(2020, 4)),
        updated_at="2026-10-03T00:00:00Z",
    )
    (good,) = captured(root, upstream, ds)
    fixed = stage(root, con, [ds])
    assert fixed.failed == {} and fixed.dropped == {ds.name: 1}
    assert [r[2] for r in table_rows(con, ds, "game_id, pts, _sha256")] == [good.sha256] * 4


def test_table_dropped_out_of_band_is_reloaded_with_fresh_meta_rows(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", parquet_bytes(rows(2020, 3)))
    release(upstream, "part_2021.parquet", parquet_bytes(rows(2021, 4)))
    ds = dataset()
    captured(root, upstream, ds)
    stage(root, con, [ds])
    con.execute(f"DROP TABLE {ds.qualified}")

    report = stage(root, con, [ds])

    assert report.loaded == {"t.parts": [("part_2020.parquet", 3), ("part_2021.parquet", 4)]}
    assert [(u, n) for u, _, _, n in staged_units(con, ds)] == [
        ("part_2020.parquet", 3),
        ("part_2021.parquet", 4),
    ]
    assert len(table_rows(con, ds)) == 7


def test_stage_with_a_registry_drops_staged_tables_no_dataset_registers_with_meta_and_schema(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", parquet_bytes(rows(2020, 3)))
    keep = dataset()
    gone = dataset(name="old.parts")
    con.execute('CREATE SCHEMA lake."old"')
    captured(root, upstream, keep, gone)
    stage(root, con, [keep, gone])
    assert staged_units(con, gone) and unit_chunks(con, gone)

    assert stage(root, con, [keep], registry=[keep]).retired == ["old.parts"]

    assert not table_exists(con, gone.schema, gone.table)
    assert staged_units(con, gone) == [] and unit_chunks(con, gone) == []
    assert "old" not in {
        s
        for (s,) in con.execute(
            "SELECT schema_name FROM duckdb_schemas() WHERE database_name = 'lake'"
        ).fetchall()
    }
    assert table_rows(con, keep, "game_id") == [(r["game_id"],) for r in rows(2020, 3)]
    assert staged_units(con, keep)
    assert retire(con, [keep]) == []


def test_staged_units_rows_match_inserted_counts_and_staged_at_is_naive_utc(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", parquet_bytes(rows(2020, 3)))
    release(upstream, "part_2021.parquet", parquet_bytes(rows(2021, 5)))
    ds = dataset()
    captured(root, upstream, ds)

    before = utcnow()
    stage(root, con, [ds])
    after = utcnow()

    meta = con.execute(
        "SELECT unit, rows, staged_at FROM lake.meta.staged_units WHERE dataset = ? ORDER BY unit",
        [ds.name],
    ).fetchall()
    counts = dict(
        con.execute(f"SELECT _unit, count(*) FROM {ds.qualified} GROUP BY _unit").fetchall()
    )
    assert [(u, n) for u, n, _ in meta] == [("part_2020.parquet", 3), ("part_2021.parquet", 5)]
    assert counts == {"part_2020.parquet": 3, "part_2021.parquet": 5}
    for _, _, staged_at in meta:
        assert staged_at.tzinfo is None
        assert before <= staged_at <= after


@pytest.mark.parametrize(
    ("have", "want", "expected"),
    [
        ("BIGINT", "BIGINT", "BIGINT"),
        ("INTEGER", "BIGINT", "BIGINT"),
        ("BIGINT", "INTEGER", "BIGINT"),
        ("BIGINT", "DOUBLE", "DOUBLE"),
        ("DOUBLE", "BIGINT", "DOUBLE"),
        ("VARCHAR", "BIGINT", "VARCHAR"),
        ("VARCHAR", "DATE", "VARCHAR"),
        ("BIGINT", "VARCHAR", None),
        ("DATE", "VARCHAR", None),
        ("DATE", "TIMESTAMP", None),
        ("BOOLEAN", "INTEGER", None),
    ],
)
def test_widen_grows_numeric_types_absorbs_into_varchar_and_never_narrows(
    have: str, want: str, expected: str | None
) -> None:
    assert widen(have, want) == expected


def null_typed_unit(n: int) -> bytes:
    ids = pa.array([f"g{i}" for i in range(n)], pa.string())
    return parquet_bytes(pa.table({"game_id": ids, "pts": pa.nulls(n, pa.null())}))


def test_column_null_in_an_early_unit_takes_the_type_of_the_first_unit_that_has_values(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", null_typed_unit(2))
    release(upstream, "part_2021.parquet", typed_unit([1.5, 2.5], pa.float64()))
    ds = dataset()
    captured(root, upstream, ds)

    report = stage(root, con, [ds])

    assert report.failed == {}
    assert columns(con, ds.qualified)["pts"] == "DOUBLE"
    assert con.execute(
        f"SELECT _unit, pts FROM {ds.qualified} ORDER BY _unit, game_id"
    ).fetchall() == [
        ("part_2020.parquet", None),
        ("part_2020.parquet", None),
        ("part_2021.parquet", 1.5),
        ("part_2021.parquet", 2.5),
    ]


def test_column_null_in_a_later_unit_inserts_null_without_changing_the_type(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", typed_unit([7, 8], pa.int64()))
    release(upstream, "part_2021.parquet", null_typed_unit(1))
    ds = dataset()
    captured(root, upstream, ds)

    report = stage(root, con, [ds])

    assert report.failed == {}
    assert columns(con, ds.qualified)["pts"] == "BIGINT"
    assert con.execute(f"SELECT pts FROM {ds.qualified} ORDER BY _unit, game_id").fetchall() == [
        (7,),
        (8,),
        (None,),
    ]


def test_column_null_in_every_unit_is_absent_from_the_staged_table(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", null_typed_unit(2))
    ds = dataset()
    captured(root, upstream, ds)

    stage(root, con, [ds])

    assert "pts" not in columns(con, ds.qualified)


def test_a_failing_unit_is_recorded_and_the_remaining_units_still_load(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.zip", zip_bytes({"a.csv": CSV}))
    release(upstream, "part_2021.zip", zip_bytes({"a.csv": CSV, "b.csv": CSV}))
    release(upstream, "part_2022.zip", zip_bytes({"a.csv": CSV}))
    ds = dataset(match=r"part_(?P<season>\d{4})\.zip", parse=Csv())
    captured(root, upstream, ds)

    report = stage(root, con, [ds])

    assert [u for u, _ in report.loaded["t.parts"]] == ["part_2020.zip", "part_2022.zip"]
    assert list(report.failed["t.parts"]) == ["part_2021.zip"]
    assert [u for u, *_ in staged_units(con, ds)] == ["part_2020.zip", "part_2022.zip"]


def test_rebuild_drops_the_table_and_reloads_every_unit_under_the_current_declaration(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    release(upstream, "part_2020.parquet", parquet_bytes(rows(2020, 50)))
    unsorted = dataset()
    captured(root, upstream, unsorted)
    stage(root, con, [unsorted])
    snapshots_before = snapshot_count(con)

    sorted_by_pts = dataset(sort=("pts", "game_id"))
    report = stage(root, con, [sorted_by_pts], rebuild=True)

    assert report.loaded == {"t.parts": [("part_2020.parquet", 50)]}
    assert len(staged_units(con, sorted_by_pts)) == 1
    # DuckLake keeps the dropped table's file for time travel, so read the live file.
    (path,) = live_files(con, sorted_by_pts)
    pts = cast(list[int], pq.read_table(path, columns=["pts"]).column("pts").to_pylist())
    assert pts == sorted(pts)
    assert snapshot_count(con) > snapshots_before
    assert stage(root, con, [sorted_by_pts]).unchanged == ["t.parts"]


def fetched(key: str, sha: str) -> FetchRecord:
    return FetchRecord(key, f"https://example.com/{key}", "v", 1, sha, "2026-10-01T00:00:00+00:00")


def wanted(*records: FetchRecord) -> dict[tuple[str, str], FetchRecord]:
    return {(r.key, r.sha256): r for r in records}


def test_plan_loads_new_units_and_does_nothing_for_staged_ones() -> None:
    a, b = fetched("a", "1"), fetched("b", "1")

    assert stage_plan(wanted(a, b), {("a", "1")}) == UnitPlan(drops=(), loads=(Load(b, ()),))
    assert stage_plan(wanted(a), {("a", "1")}) == UnitPlan(drops=(), loads=())


def test_plan_replaces_a_new_version_in_its_load_and_drops_a_vanished_unit_alone() -> None:
    new = fetched("a", "2")

    plan = stage_plan(wanted(new), {("a", "1"), ("gone", "9")})

    assert plan == UnitPlan(drops=(("gone", "9"),), loads=(Load(new, ("1",)),))


def test_plan_keeps_every_wanted_snapshot_of_one_key() -> None:
    first, second = fetched("injuries_2027.parquet", "1"), fetched("injuries_2027.parquet", "2")

    plan = stage_plan(wanted(first, second), {("injuries_2027.parquet", "1")})

    assert plan == UnitPlan(drops=(), loads=(Load(second, ()),))


class CountingConnection:
    """Passes every call to the connection and keeps each SQL statement it ran."""

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self.con = con
        self.statements: list[str] = []

    def execute(self, sql: str, *args: object) -> duckdb.DuckDBPyConnection:
        self.statements.append(sql)
        return self.con.execute(sql, *args)

    def __getattr__(self, name: str) -> object:
        return getattr(self.con, name)


def test_a_csv_unit_is_read_four_times_into_a_new_table_and_three_into_an_existing_one(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    """Pins the passes: two sniffing DESCRIBEs, the empty CREATE for a new table, the INSERT."""
    for season in (2020, 2021):
        release(upstream, f"part_{season}.csv", CSV)
    ds = dataset(match=r"part_(?P<season>\d{4})\.csv", parse=Csv())
    captured(root, upstream, ds)
    counting = CountingConnection(con)

    stage(root, counting, [ds])  # type: ignore[arg-type]

    reads = [s.split()[0] for s in counting.statements if "read_csv(" in s]
    assert sorted(reads) == [
        "CREATE",
        "DESCRIBE",
        "DESCRIBE",
        "DESCRIBE",
        "DESCRIBE",
        "INSERT",
        "INSERT",
    ]


def unit_chunks(con: duckdb.DuckDBPyConnection, ds: Dataset) -> list[tuple]:
    return con.execute(
        "SELECT unit, column_name, value FROM lake.meta.unit_chunks WHERE dataset = ? ORDER BY ALL",
        [ds.name],
    ).fetchall()


def test_a_staged_unit_records_its_chunk_column_values_and_a_restage_replaces_them(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    two_seasons = [
        {"game_id": "a", "pts": 1, "season": 2019},
        {"game_id": "b", "pts": 2, "season": 2020},
    ]
    release(upstream, "part_2020.parquet", parquet_bytes(two_seasons))
    ds = dataset()
    captured(root, upstream, ds)
    stage(root, con, [ds])

    assert unit_chunks(con, ds) == [
        ("part_2020.parquet", "season", "2019"),
        ("part_2020.parquet", "season", "2020"),
    ]

    release(upstream, "part_2020.parquet", parquet_bytes(two_seasons[1:]), "2026-10-02T00:00:00Z")
    captured(root, upstream, ds)
    stage(root, con, [ds])

    assert unit_chunks(con, ds) == [("part_2020.parquet", "season", "2020")]


def test_a_unit_gone_upstream_or_a_rebuild_takes_its_chunk_values_with_it(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    for season in (2020, 2021):
        release(upstream, f"part_{season}.parquet", parquet_bytes(rows(season, 1)))
    ds = dataset()
    captured(root, upstream, ds)
    stage(root, con, [ds])
    con.execute(
        "INSERT INTO lake.meta.staged_units SELECT dataset, 'part_1999.parquet', 'gone', '', 1, "
        "now() FROM lake.meta.staged_units LIMIT 1"
    )
    con.execute(
        "INSERT INTO lake.meta.unit_chunks VALUES "
        "(?, 'part_1999.parquet', 'gone', 'season', '1999')",
        [ds.name],
    )

    report = stage(root, con, [ds])
    after_drop = unit_chunks(con, ds)
    stage(root, con, [ds], rebuild=True)

    assert report.dropped == {"t.parts": 1}
    assert {u for u, _, _ in after_drop} == {"part_2020.parquet", "part_2021.parquet"}
    assert unit_chunks(con, ds) == after_drop


def test_units_staged_before_chunks_were_recorded_are_backfilled_by_the_next_stage(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    for season in (2020, 2021):
        release(upstream, f"part_{season}.parquet", parquet_bytes(rows(season, 2)))
    ds = dataset()
    captured(root, upstream, ds)
    stage(root, con, [ds])
    recorded = unit_chunks(con, ds)
    con.execute("DELETE FROM lake.meta.unit_chunks WHERE unit = 'part_2021.parquet'")

    report = stage(root, con, [ds])

    assert report.unchanged == ["t.parts"]
    assert unit_chunks(con, ds) == recorded


def test_a_hand_downloaded_file_flows_from_the_drop_folder_through_capture_into_a_staged_table(
    root: Root, con: duckdb.DuckDBPyConnection, upstream: FakeUpstream
) -> None:
    ds = dataset(
        name="t.grades",
        fetch=DropFolder("acme", r"(?P<season>\d{4})/grades\.csv"),
        parse=Csv(),
    )
    drop = root.drop / "acme" / "2020"
    drop.mkdir(parents=True)
    (drop / "grades.csv").write_bytes(csv_bytes(["player", "grade"], [("a", 90), ("b", 80)]))

    assert capture(root, [ds], client=upstream.client).failed == {}
    report = stage(root, con, [ds])

    assert report.failed == {}
    assert con.execute(
        f"SELECT season, player, grade FROM {ds.qualified} ORDER BY player"
    ).fetchall() == [(2020, "a", 90), (2020, "b", 80)]
