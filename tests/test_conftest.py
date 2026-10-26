from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from nbalake.capture import FetchRecord, capture
from nbalake.lake import Root, table_exists
from nbalake.model import GitDir, Kaggle
from nbalake.stage import materialized
from tests.conftest import (
    GITHUB_API,
    FakeUpstream,
    csv_bytes,
    dataset,
    git_blob_sha,
    parquet_bytes,
    write_csv,
    write_parquet,
    write_tar_xz,
    write_zip,
)

PAYLOAD = parquet_bytes([{"season": 2020, "pts": 101}, {"season": 2020, "pts": 99}])


def test_capture_fetches_one_release_asset_into_the_raw_store(
    root: Root, upstream: FakeUpstream
) -> None:
    url = upstream.add_release_asset("o/r", "tag", "part_2020.parquet", PAYLOAD)

    report = capture(root, [dataset()], client=upstream.client, index=upstream.index)

    assert report.skipped == 0 and report.failed == {}
    (rec,) = report.fetched
    sha = hashlib.sha256(PAYLOAD).hexdigest()
    assert rec == FetchRecord(
        key="part_2020.parquet",
        url=url,
        version=f"2026-10-01T00:00:00Z:{len(PAYLOAD)}",
        size=len(PAYLOAD),
        sha256=sha,
        fetched_at=rec.fetched_at,
    )
    assert root.blob(sha).read_bytes() == PAYLOAD
    lines = root.fetches.read_text().splitlines()
    assert len(lines) == 1
    assert FetchRecord.from_json(lines[0]) == rec


def test_release_listing_paginates_past_one_hundred_releases(upstream: FakeUpstream) -> None:
    upstream.pad_releases("o/r", 100)
    upstream.add_release_asset("o/r", "tag", "part_2020.parquet", PAYLOAD)

    units = upstream.index.units(dataset().fetch)

    assert [u.key for u in units] == ["part_2020.parquet"]
    assert upstream.request_log == [
        f"{GITHUB_API}/repos/o/r/releases?per_page=100&page=1",
        f"{GITHUB_API}/repos/o/r/releases?per_page=100&page=2",
    ]


def test_git_blob_sha_matches_git_hash_object() -> None:
    assert git_blob_sha(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    assert git_blob_sha(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_git_dir_listing_serves_sha_versions_and_download_urls(
    root: Root, upstream: FakeUpstream
) -> None:
    body = csv_bytes(["a", "b"], [[1, 2]])
    url = upstream.add_git_file("own/repo", "master", "data/dir", "file_2020.csv", body)
    upstream.add_git_dir("own/repo", "master", "data/dir", "nested")
    fetch = GitDir("own/repo", "data/dir", r"file_(?P<season>\d{4})\.csv", ref="master")

    (unit,) = upstream.index.units(fetch)
    report = capture(root, [dataset(fetch=fetch)], client=upstream.client, index=upstream.index)

    assert (unit.key, unit.url, unit.version, unit.size) == (
        "file_2020.csv",
        url,
        git_blob_sha(body),
        len(body),
    )
    assert url.startswith(fetch.url_prefix)
    assert root.blob(report.fetched[0].sha256).read_bytes() == body


def test_kaggle_download_redirects_to_storage_and_serves_bytes(
    root: Root, upstream: FakeUpstream
) -> None:
    archive = b"PK\x03\x04 not really a zip"
    download = upstream.set_kaggle("own", "slug", archive, version=3)
    fetch = Kaggle("own", "slug")

    report = capture(root, [dataset(fetch=fetch)], client=upstream.client, index=upstream.index)

    (rec,) = report.fetched
    assert (rec.key, rec.url, rec.version, rec.size) == ("slug.zip", download, "v3", len(archive))
    assert download.startswith(fetch.url_prefix)
    assert root.blob(rec.sha256).read_bytes() == archive
    assert upstream.request_log == [
        "https://www.kaggle.com/api/v1/datasets/view/own/slug",
        download,
        "https://storage.googleapis.com/kaggle-data-sets/own/slug/v3/archive.zip",
    ]


def test_fail_next_aborts_one_download_mid_stream_then_recovers(
    root: Root, upstream: FakeUpstream
) -> None:
    url = upstream.add_release_asset("o/r", "tag", "part_2020.parquet", PAYLOAD)
    upstream.fail_next(url)

    failed = capture(root, [dataset()], client=upstream.client, index=upstream.index)
    recovered = capture(root, [dataset()], client=upstream.client, index=upstream.index)

    assert failed.fetched == [] and list(failed.failed) == [url]
    assert failed.failed[url].startswith("ReadError")
    assert len(recovered.fetched) == 1
    assert root.blob(recovered.fetched[0].sha256).read_bytes() == PAYLOAD
    assert upstream.request_log.count(url) == 2


def test_fail_next_on_a_redirect_fails_the_target_it_redirects_to(upstream: FakeUpstream) -> None:
    download = upstream.set_kaggle("own", "slug", b"x" * 1000)
    upstream.fail_next(download)

    with pytest.raises(httpx.ReadError):
        upstream.client.get(download)
    assert upstream.client.get(download).content == b"x" * 1000


def test_unknown_urls_return_404(upstream: FakeUpstream) -> None:
    assert (
        upstream.client.get("https://github.com/o/r/releases/download/tag/x.parquet").status_code
        == 404
    )
    with pytest.raises(httpx.HTTPStatusError):
        upstream.index.units(dataset(repo="nobody/nothing").fetch)
    with pytest.raises(httpx.HTTPStatusError):
        upstream.index.units(GitDir("o/r", "missing", r".*"))
    with pytest.raises(httpx.HTTPStatusError):
        upstream.index.units(Kaggle("own", "missing"))


def test_con_opens_a_fresh_lake_with_schema_t_and_meta_tables(root: Root, con) -> None:
    schemas = {
        s
        for (s,) in con.execute(
            "SELECT schema_name FROM duckdb_schemas() WHERE database_name = 'lake'"
        ).fetchall()
    }
    assert {"meta", "t"} <= schemas
    assert all(table_exists(con, "meta", t) for t in ("runs", "staged_units", "gate_results"))
    assert root.catalog.exists() and root.data.is_dir()


def test_parquet_and_csv_helpers_are_readable_by_duckdb(tmp_path: Path, con) -> None:
    pqt = write_parquet(tmp_path / "p.parquet", [{"a": 1, "b": "x"}, {"a": 2, "b": None}])
    csvf = write_csv(tmp_path / "c.csv", ["a", "b"], [[1, "x"], [2, None]])

    assert con.execute(f"SELECT a, b FROM read_parquet('{pqt}') ORDER BY a").fetchall() == [
        (1, "x"),
        (2, None),
    ]
    assert con.execute(
        f"SELECT a, b FROM read_csv('{csvf}', header=true) ORDER BY a"
    ).fetchall() == [
        (1, "x"),
        (2, None),
    ]


def test_archive_helpers_round_trip_through_materialized(root: Root, tmp_path: Path) -> None:
    body = csv_bytes(["a"], [[1]])
    archives = (
        write_zip(tmp_path / "one.zip", {"inner.csv": body}),
        write_tar_xz(tmp_path / "one.tar.xz", {"inner.csv": body}),
    )
    for archive in archives:
        with materialized(root, archive, None) as path:
            assert path.name.endswith("inner.csv") and path.read_bytes() == body
        assert not path.exists()
