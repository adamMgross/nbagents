from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import date
from functools import partial
from pathlib import Path

import httpx
import pytest

from nbalake.capture import (
    FetchRecord,
    Index,
    RawStore,
    capture,
    github_headers,
    make_client,
    missing_dates,
    units_in_store,
)
from nbalake.lake import Root
from nbalake.model import Csv, Dataset, DropFolder, GitDir, GitTree, Kaggle, ReleaseAssets, Versions
from tests.conftest import (
    GITHUB_API,
    KAGGLE_API,
    KAGGLE_STORAGE,
    FakeUpstream,
    dataset,
    git_blob_sha,
)

PAYLOAD = b"season,pts\n2020,101\n" * 50
RELEASES_URL = f"{GITHUB_API}/repos/o/r/releases"
GIT_FETCH = GitDir("o/r", "data", r"part_(?P<season>\d{4})\.csv")
KAGGLE_FETCH = Kaggle("own", "slug")
DROP_FETCH = DropFolder("acme", r"(?P<season>\d{4})/grades\.csv")
TREE_FETCH = GitTree("o/r", r"(?P<season>\d{4})/(?P<po>playoffs/)?shots/(?P<band>open|tight)\.csv")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob_files(root: Root) -> list[Path]:
    return sorted(p for p in root.blobs.rglob("*") if p.is_file())


def download_requests(upstream: FakeUpstream, urls: list[str]) -> int:
    return sum(upstream.request_log.count(url) for url in urls)


def run_capture(root: Root, upstream: FakeUpstream, datasets: list[Dataset], **kw: object):
    return capture(root, datasets, client=upstream.client, index=upstream.index, **kw)  # type: ignore[arg-type]


def publish_asset(
    upstream: FakeUpstream, data: bytes = PAYLOAD, updated_at: str = "2026-10-01T00:00:00Z"
) -> str:
    return upstream.add_release_asset(
        "o/r", "tag", "part_2020.parquet", data, updated_at=updated_at
    )


def publish_git(upstream: FakeUpstream, data: bytes) -> str:
    return upstream.add_git_file("o/r", "main", "data", "part_2020.csv", data)


def publish_kaggle(upstream: FakeUpstream, version: int) -> str:
    return upstream.set_kaggle("own", "slug", b"PK\x03\x04 archive", version=version)


def record(
    key: str, url: str, version: str = "v1", fetched_at: str = "2026-10-01T00:00:00+00:00"
) -> FetchRecord:
    return FetchRecord(
        key=key,
        url=url,
        version=version,
        size=1,
        sha256=sha256(url.encode()),
        fetched_at=fetched_at,
    )


def test_already_captured_version_is_skipped_without_a_download(
    root: Root, upstream: FakeUpstream
) -> None:
    urls = [
        upstream.add_release_asset("o/r", "tag", f"part_{season}.parquet", PAYLOAD)
        for season in (2020, 2021)
    ]
    first = run_capture(root, upstream, [dataset()])
    seen = len(upstream.request_log)

    second = run_capture(root, upstream, [dataset()])

    assert len(first.fetched) == 2
    assert (second.fetched, second.skipped, second.failed) == ([], 2, {})
    assert upstream.request_log[seen:] == [f"{RELEASES_URL}?per_page=100&page=1"]
    assert download_requests(upstream, urls) == 2
    assert len(RawStore(root).records()) == 2


@pytest.mark.parametrize(
    ("ds", "publish", "republish"),
    [
        pytest.param(
            dataset(),
            publish_asset,
            partial(publish_asset, updated_at="2026-10-02T00:00:00Z"),
            id="asset_updated_at",
        ),
        pytest.param(
            dataset(),
            publish_asset,
            partial(publish_asset, data=PAYLOAD + b"\n"),
            id="asset_size",
        ),
        pytest.param(
            dataset(fetch=GIT_FETCH),
            partial(publish_git, data=b"a,b\n1,2\n"),
            partial(publish_git, data=b"a,b\n1,3\n"),
            id="git_blob_sha",
        ),
        pytest.param(
            dataset(fetch=KAGGLE_FETCH),
            partial(publish_kaggle, version=1),
            partial(publish_kaggle, version=2),
            id="kaggle_version",
        ),
    ],
)
def test_changed_version_token_is_refetched_and_appended_after_the_old_line(
    root: Root,
    upstream: FakeUpstream,
    ds: Dataset,
    publish: Callable[[FakeUpstream], str],
    republish: Callable[[FakeUpstream], str],
) -> None:
    url = publish(upstream)
    first = run_capture(root, upstream, [ds])
    assert republish(upstream) == url

    second = run_capture(root, upstream, [ds])

    (old,), (new,) = first.fetched, second.fetched
    assert (second.skipped, second.failed) == (0, {})
    assert old.url == new.url == url
    assert old.version != new.version
    assert RawStore(root).records() == [old, new]
    assert root.blob(new.sha256).exists()


def test_identical_bytes_from_two_urls_share_one_blob_and_get_two_lines(
    root: Root, upstream: FakeUpstream
) -> None:
    for season in (2020, 2021):
        upstream.add_release_asset("o/r", "tag", f"part_{season}.parquet", PAYLOAD)

    report = run_capture(root, upstream, [dataset()])

    records = RawStore(root).records()
    assert len(report.fetched) == 2
    assert {r.sha256 for r in records} == {sha256(PAYLOAD)}
    assert len({r.url for r in records}) == 2
    assert blob_files(root) == [root.blob(sha256(PAYLOAD))]


def test_a_unit_matched_by_two_datasets_is_downloaded_once(
    root: Root, upstream: FakeUpstream
) -> None:
    url = publish_asset(upstream)
    both = [dataset(name="t.a"), dataset(name="t.b", match=r"part_\d{4}\.parquet")]

    report = run_capture(root, upstream, both)

    assert (len(report.fetched), report.skipped, report.failed) == (1, 0, {})
    assert upstream.request_log.count(url) == 1
    assert len(RawStore(root).records()) == 1


def test_failed_download_leaves_no_blob_or_line_while_other_units_succeed(
    root: Root, upstream: FakeUpstream
) -> None:
    good, bad = b"good\n" * 1000, b"bad\n" * 1000
    good_url = upstream.add_release_asset("o/r", "tag", "part_2020.parquet", good)
    bad_url = upstream.add_release_asset("o/r", "tag", "part_2021.parquet", bad)
    upstream.fail_next(bad_url)

    report = run_capture(root, upstream, [dataset()])

    assert [r.url for r in report.fetched] == [good_url]
    assert list(report.failed) == [bad_url]
    assert report.failed[bad_url].startswith("ReadError")
    assert not root.blob(sha256(bad)).exists()
    assert blob_files(root) == [root.blob(sha256(good))]
    assert [r.url for r in RawStore(root).records()] == [good_url]


def test_failed_download_leaves_no_part_file_in_tmp(root: Root, upstream: FakeUpstream) -> None:
    # Over 2 MiB so one full 1 MiB chunk reaches the .part file before the fake raises.
    url = publish_asset(upstream, data=bytes(3 << 20))
    upstream.fail_next(url)

    report = run_capture(root, upstream, [dataset()])

    assert list(report.failed) == [url]
    assert list(root.tmp.iterdir()) == []


def test_concurrent_downloads_append_whole_lines_to_fetches_jsonl(
    root: Root, upstream: FakeUpstream
) -> None:
    payloads = {f"part_{2000 + i}.parquet": f"unit {i}\n".encode() * 200 for i in range(40)}
    for name, data in payloads.items():
        upstream.add_release_asset("o/r", "tag", name, data)

    report = run_capture(root, upstream, [dataset()], concurrency=8)

    text = root.fetches.read_text(encoding="utf-8")
    records = [FetchRecord.from_json(line) for line in text.splitlines()]
    assert (len(report.fetched), report.failed) == (40, {})
    assert text.endswith("\n") and text.count("\n") == 40
    assert {r.key for r in records} == set(payloads)
    assert all(root.blob(r.sha256).read_bytes() == payloads[r.key] for r in records)
    assert report.bytes == sum(len(d) for d in payloads.values())


def test_capture_limit_caps_fetched_units_and_leaves_the_rest_for_next_time(
    root: Root, upstream: FakeUpstream
) -> None:
    urls = [
        upstream.add_release_asset("o/r", "tag", f"part_{season}.parquet", PAYLOAD)
        for season in range(2016, 2021)
    ]

    first = run_capture(root, upstream, [dataset()], limit=2)
    second = run_capture(root, upstream, [dataset()])

    assert (len(first.fetched), first.skipped, first.failed) == (2, 0, {})
    assert (len(second.fetched), second.skipped, second.failed) == (3, 2, {})
    assert download_requests(upstream, urls) == 5
    assert sorted(r.url for r in first.fetched + second.fetched) == sorted(urls)


def test_index_units_requires_the_whole_name_to_match(upstream: FakeUpstream) -> None:
    for name in ("x_2020.parquet", "x_2020.parquet.bak", "prefix_x_2020.parquet"):
        upstream.add_release_asset("o/r", "tag", name, PAYLOAD)

    units = upstream.index.units(ReleaseAssets("tag", r"x_(?P<season>\d{4})\.parquet", repo="o/r"))

    assert [u.key for u in units] == ["x_2020.parquet"]


def test_release_listing_is_paged_once_per_repo_across_datasets(
    root: Root, upstream: FakeUpstream
) -> None:
    upstream.pad_releases("o/r", 100)
    tags = [f"season-{year}" for year in range(2016, 2021)]
    for tag in tags:
        upstream.add_release_asset("o/r", tag, "part_2020.parquet", PAYLOAD)
    datasets = [dataset(name=f"t.{tag.replace('-', '_')}", tag=tag) for tag in tags]

    report = run_capture(root, upstream, datasets)

    listing = [u for u in upstream.request_log if u.startswith(RELEASES_URL)]
    assert listing == [f"{RELEASES_URL}?per_page=100&page={p}" for p in (1, 2)]
    assert sorted(r.url.split("/")[-2] for r in report.fetched) == tags
    assert report.failed == {}


def test_git_dir_listing_ignores_entries_that_are_not_files(upstream: FakeUpstream) -> None:
    upstream.add_git_file("o/r", "main", "data", "part_2020.csv", b"a\n1\n")
    upstream.add_git_dir("o/r", "main", "data", "part_2021.csv")

    units = upstream.index.units(GIT_FETCH)

    assert [u.key for u in units] == ["part_2020.csv"]


def test_git_tree_units_match_full_paths_in_every_directory_and_skip_trees(
    upstream: FakeUpstream,
) -> None:
    regular = upstream.add_git_tree_file("o/r", "main", "2020/shots/open.csv", b"a\n1\n")
    playoffs = upstream.add_git_tree_file("o/r", "main", "2021/playoffs/shots/tight.csv", b"a\n2\n")
    upstream.add_git_tree_file("o/r", "main", "2021/shots/team.csv", b"a\n3\n")
    upstream.add_git_tree_dir("o/r", "main", "2022/shots/open.csv")

    units = upstream.index.units(TREE_FETCH)

    assert [(u.key, u.url, u.version) for u in units] == [
        ("2020/shots/open.csv", regular, git_blob_sha(b"a\n1\n")),
        ("2021/playoffs/shots/tight.csv", playoffs, git_blob_sha(b"a\n2\n")),
    ]
    assert regular == "https://raw.githubusercontent.com/o/r/main/2020/shots/open.csv"


def test_git_tree_recapture_downloads_only_the_files_whose_blob_changed(
    root: Root, upstream: FakeUpstream
) -> None:
    ds = dataset(fetch=TREE_FETCH)
    upstream.add_git_tree_file("o/r", "main", "2020/shots/open.csv", b"a\n1\n")
    upstream.add_git_tree_file("o/r", "main", "2021/shots/open.csv", b"a\n2\n")
    first = run_capture(root, upstream, [ds])

    changed = upstream.add_git_tree_file("o/r", "main", "2021/shots/open.csv", b"a\n2\n3\n")
    second = run_capture(root, upstream, [ds])

    assert sorted(r.key for r in first.fetched) == ["2020/shots/open.csv", "2021/shots/open.csv"]
    assert [(r.key, r.url) for r in second.fetched] == [("2021/shots/open.csv", changed)]
    latest = units_in_store(ds, RawStore(root).records())
    assert [(r.key, root.blob(r.sha256).read_bytes()) for r in latest] == [
        ("2020/shots/open.csv", b"a\n1\n"),
        ("2021/shots/open.csv", b"a\n2\n3\n"),
    ]


def test_a_truncated_git_tree_fails_the_listing_instead_of_missing_units(
    upstream: FakeUpstream,
) -> None:
    upstream.add_git_tree_file("o/r", "main", "2020/shots/open.csv", b"a\n1\n")
    upstream.truncate_tree("o/r", "main")

    with pytest.raises(ValueError, match="truncated"):
        upstream.index.units(TREE_FETCH)


def test_kaggle_download_follows_the_redirect_and_versions_by_current_version_number(
    root: Root, upstream: FakeUpstream
) -> None:
    archive = b"PK\x03\x04 archive v7"
    download = upstream.set_kaggle("own", "slug", archive, version=7)

    report = run_capture(root, upstream, [dataset(fetch=KAGGLE_FETCH)])

    (rec,) = report.fetched
    assert (rec.key, rec.url, rec.version, rec.size) == ("slug.zip", download, "v7", len(archive))
    assert root.blob(rec.sha256).read_bytes() == archive
    assert upstream.request_log == [
        f"{KAGGLE_API}/datasets/view/own/slug",
        download,
        f"{KAGGLE_STORAGE}/own/slug/v7/archive.zip",
    ]


def test_authorization_header_is_sent_only_when_github_token_is_set(
    upstream: FakeUpstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish_asset(upstream)

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with httpx.Client(transport=upstream.transport, headers=github_headers()) as anonymous:
        Index(anonymous).units(dataset().fetch)
    with make_client() as anonymous_default:
        assert "authorization" not in anonymous_default.headers

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    with httpx.Client(transport=upstream.transport, headers=github_headers()) as authed:
        Index(authed).units(dataset().fetch)
    with make_client() as authed_default:
        assert authed_default.headers["authorization"] == "Bearer ghp_test"

    anonymous_request, authed_request = upstream.requests
    assert "authorization" not in anonymous_request.headers
    assert authed_request.headers["authorization"] == "Bearer ghp_test"
    assert authed_request.headers["accept"] == "application/vnd.github+json"


def test_fetch_records_tolerate_blank_lines_and_unknown_fields(root: Root) -> None:
    rec = record(
        "part_2020.parquet", "https://github.com/o/r/releases/download/tag/part_2020.parquet"
    )
    line = json.dumps(asdict(rec) | {"etag": "W/abc"})
    root.ensure()
    root.fetches.write_text(f"{line}\n\n{line}\n", encoding="utf-8")

    assert RawStore(root).records() == [rec, rec]
    assert FetchRecord.from_json(line) == rec


PREFIX = "https://github.com/o/r/releases/download/tag/"
STORE = [
    record("part_2021.parquet", f"{PREFIX}part_2021.parquet"),
    record("part_2020.parquet", f"{PREFIX}part_2020.parquet", "v2", "2026-10-02T00:00:00+00:00"),
    record("part_2020.parquet", f"{PREFIX}part_2020.parquet", "v1", "2026-10-01T00:00:00+00:00"),
    record("part_2020.parquet", "https://github.com/o/r/releases/download/other/part_2020.parquet"),
    record("part_2020.parquet", "https://github.com/x/y/releases/download/tag/part_2020.parquet"),
    record("notes.txt", f"{PREFIX}notes.txt"),
]


def test_units_in_store_returns_the_latest_capture_per_key_for_versions_latest() -> None:
    picked = units_in_store(dataset(), STORE)

    assert [(r.key, r.version) for r in picked] == [
        ("part_2020.parquet", "v2"),
        ("part_2021.parquet", "v1"),
    ]


def test_units_in_store_returns_every_capture_oldest_first_for_versions_all() -> None:
    picked = units_in_store(dataset(versions=Versions.ALL), STORE)

    assert [(r.key, r.version) for r in picked] == [
        ("part_2020.parquet", "v1"),
        ("part_2020.parquet", "v2"),
        ("part_2021.parquet", "v1"),
    ]


def test_units_in_store_ignores_other_tags_repos_and_non_matching_keys() -> None:
    for versions in Versions:
        picked = units_in_store(dataset(versions=versions), STORE)
        assert all(r.url.startswith(PREFIX) for r in picked)
        assert all(r.key != "notes.txt" for r in picked)

    other_tag = units_in_store(dataset(tag="other"), STORE)
    assert [r.url for r in other_tag] == [
        "https://github.com/o/r/releases/download/other/part_2020.parquet"
    ]


def test_units_in_store_keeps_the_last_written_line_when_fetched_at_ties() -> None:
    older = record("part_2020.parquet", f"{PREFIX}part_2020.parquet", "v1")
    newer = replace(older, version="v2", sha256=sha256(b"v2"))

    assert units_in_store(dataset(), [older, newer]) == [newer]


def test_units_in_store_ignores_a_kaggle_dataset_whose_slug_extends_this_one() -> None:
    records = [
        record("nba.zip", f"{KAGGLE_API}/datasets/download/own/nba"),
        record("nba-extended.zip", f"{KAGGLE_API}/datasets/download/own/nba-extended"),
    ]

    picked = units_in_store(dataset(fetch=Kaggle("own", "nba")), records)

    assert [r.key for r in picked] == ["nba.zip"]


def snapshot(day: str, key: str = "injuries_2027.parquet") -> FetchRecord:
    url = f"https://github.com/o/r/releases/download/tag/{key}"
    return FetchRecord(key, url, f"{day}T11:00:00Z:1", 1, day, f"{day}T12:00:00+00:00")


def test_missing_dates_are_the_days_a_snapshot_dataset_was_not_captured() -> None:
    ds = dataset(match=r"injuries_(?P<season>\d{4})\.parquet", versions=Versions.ALL)
    records = [snapshot(d) for d in ("2026-10-21", "2026-10-22", "2026-10-24", "2026-10-24")]

    assert missing_dates(ds, records, through=date(2026, 10, 26)) == [
        date(2026, 10, 23),
        date(2026, 10, 25),
        date(2026, 10, 26),
    ]
    assert missing_dates(ds, [], through=date(2026, 10, 26)) == []
    assert missing_dates(ds, records[:2], through=date(2026, 10, 22)) == []


def drop_dataset() -> Dataset:
    return dataset(name="t.grades", fetch=DROP_FETCH, parse=Csv())


def put_drop(root: Root, relative: str, data: bytes) -> Path:
    path = root.drop / "acme" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_drop_folder_units_match_the_path_relative_to_the_vendor_folder_in_nested_folders(
    root: Root, upstream: FakeUpstream
) -> None:
    put_drop(root, "2020/grades.csv", b"a\n1\n")
    put_drop(root, "2021/grades.csv", b"a\n2\n")
    put_drop(root, "2021/notes.txt", b"not data")
    put_drop(root, "other/2022/grades.csv", b"a\n3\n")

    report = capture(root, [drop_dataset()], client=upstream.client)

    assert sorted((r.key, r.url) for r in report.fetched) == [
        ("2020/grades.csv", "drop://acme/2020/grades.csv"),
        ("2021/grades.csv", "drop://acme/2021/grades.csv"),
    ]
    assert upstream.request_log == []
    assert {root.blob(r.sha256).read_bytes() for r in report.fetched} == {b"a\n1\n", b"a\n2\n"}


def test_an_unchanged_drop_file_is_skipped_on_recapture(root: Root, upstream: FakeUpstream) -> None:
    put_drop(root, "2020/grades.csv", b"a\n1\n")
    capture(root, [drop_dataset()], client=upstream.client)

    second = capture(root, [drop_dataset()], client=upstream.client)

    assert (second.fetched, second.skipped, second.failed) == ([], 1, {})
    assert len(RawStore(root).records()) == 1


def test_a_changed_drop_file_is_a_new_version_and_the_old_blob_stays(
    root: Root, upstream: FakeUpstream
) -> None:
    path = put_drop(root, "2020/grades.csv", b"a\n1\n")
    first = capture(root, [drop_dataset()], client=upstream.client).fetched[0]
    path.write_bytes(b"a\n9\n")

    second = capture(root, [drop_dataset()], client=upstream.client).fetched[0]

    assert first.version == sha256(b"a\n1\n") and second.version == sha256(b"a\n9\n")
    assert root.blob(first.sha256).read_bytes() == b"a\n1\n"
    assert [r.sha256 for r in units_in_store(drop_dataset(), RawStore(root).records())] == [
        second.sha256
    ]


def test_a_deleted_drop_file_keeps_its_raw_copy(root: Root, upstream: FakeUpstream) -> None:
    path = put_drop(root, "2020/grades.csv", b"a\n1\n")
    first = capture(root, [drop_dataset()], client=upstream.client).fetched[0]
    path.unlink()

    again = capture(root, [drop_dataset()], client=upstream.client)

    assert (again.fetched, again.failed) == ([], {})
    assert root.blob(first.sha256).read_bytes() == b"a\n1\n"
    assert [r.key for r in units_in_store(drop_dataset(), RawStore(root).records())] == [
        "2020/grades.csv"
    ]


def test_a_missing_drop_folder_yields_no_units_instead_of_an_error(
    root: Root, upstream: FakeUpstream
) -> None:
    report = capture(root, [drop_dataset()], client=upstream.client)

    assert (report.fetched, report.skipped, report.failed) == ([], 0, {})


def test_another_vendors_drop_files_are_not_claimed(root: Root, upstream: FakeUpstream) -> None:
    other = root.drop / "other" / "2020"
    other.mkdir(parents=True)
    (other / "grades.csv").write_bytes(b"a\n1\n")

    report = capture(root, [drop_dataset()], client=upstream.client)

    assert report.fetched == []
