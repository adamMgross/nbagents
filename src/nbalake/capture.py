from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, TypedDict, cast

import httpx

from nbalake.lake import Root
from nbalake.model import (
    Dataset,
    DropFolder,
    Fetch,
    GitDir,
    GitTree,
    Kaggle,
    ReleaseAssets,
    Unit,
    Versions,
)

GITHUB_API = "https://api.github.com"
KAGGLE_API = "https://www.kaggle.com/api/v1"
CHUNK = 1 << 20


@dataclass(frozen=True, slots=True)
class FetchRecord:
    key: str
    url: str
    version: str
    size: int
    sha256: str
    fetched_at: str

    @classmethod
    def from_json(cls, line: str) -> FetchRecord:
        d = json.loads(line)
        return cls(**{k: d[k] for k in cls.__dataclass_fields__})


class RawStore:
    def __init__(self, root: Root) -> None:
        self.root = root
        self._lock = threading.Lock()

    def records(self) -> list[FetchRecord]:
        if not self.root.fetches.exists():
            return []
        with self.root.fetches.open(encoding="utf-8") as f:
            return [FetchRecord.from_json(line) for line in f if line.strip()]

    def versions(self) -> set[tuple[str, str]]:
        return {(r.url, r.version) for r in self.records()}

    def put(self, unit: Unit, chunks: Iterable[bytes]) -> FetchRecord:
        self.root.ensure()
        digest = hashlib.sha256()
        size = 0
        stem = hashlib.sha1(unit.url.encode()).hexdigest()[:12]
        tmp = self.root.tmp / f"{os.getpid()}-{threading.get_ident()}-{stem}.part"
        try:
            with tmp.open("wb") as out:
                for chunk in chunks:
                    digest.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        sha = digest.hexdigest()
        dest = self.root.blob(sha)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            tmp.unlink()
        else:
            os.replace(tmp, dest)
        rec = FetchRecord(
            key=unit.key,
            url=unit.url,
            version=unit.version,
            size=size,
            sha256=sha,
            fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        line = json.dumps(asdict(rec), separators=(",", ":")) + "\n"
        with self._lock, self.root.fetches.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        return rec


class ReleaseAsset(TypedDict):
    name: str
    browser_download_url: str
    updated_at: str
    size: int


class Release(TypedDict):
    tag_name: str
    assets: list[ReleaseAsset]


class ContentItem(TypedDict):
    name: str
    download_url: str
    sha: str
    size: int
    type: str


class TreeEntry(TypedDict):
    path: str
    type: str
    sha: str
    size: int


class KaggleDataset(TypedDict):
    currentVersionNumber: int
    totalBytes: int | None


class Index:
    """Lists upstream units. One listing per repo or dataset per instance, cached."""

    def __init__(
        self,
        client: httpx.Client,
        github_api: str = GITHUB_API,
        kaggle_api: str = KAGGLE_API,
        drop: Path | None = None,
    ):
        self.client = client
        self.drop = drop
        self.github_api = github_api
        self.kaggle_api = kaggle_api
        self._releases: dict[str, dict[str, list[ReleaseAsset]]] = {}
        self._dirs: dict[tuple[str, str, str], list[ContentItem]] = {}
        self._trees: dict[tuple[str, str], list[TreeEntry]] = {}
        self._kaggle: dict[tuple[str, str], Unit] = {}

    def _get_json(self, url: str, params: dict[str, str | int] | None = None) -> Any:
        r = self.client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def _release_assets(self, repo: str) -> dict[str, list[ReleaseAsset]]:
        if repo not in self._releases:
            by_tag: dict[str, list[ReleaseAsset]] = {}
            page = 1
            while True:
                payload = self._get_json(
                    f"{self.github_api}/repos/{repo}/releases", {"per_page": 100, "page": page}
                )
                assert isinstance(payload, list)
                rels = cast(list[Release], payload)
                for rel in rels:
                    by_tag[rel["tag_name"]] = rel["assets"]
                if len(rels) < 100:
                    break
                page += 1
            self._releases[repo] = by_tag
        return self._releases[repo]

    def _dir(self, repo: str, path: str, ref: str) -> list[ContentItem]:
        k = (repo, path, ref)
        if k not in self._dirs:
            items = self._get_json(
                f"{self.github_api}/repos/{repo}/contents/{path}", {"ref": ref, "per_page": 1000}
            )
            assert isinstance(items, list)
            self._dirs[k] = [i for i in cast(list[ContentItem], items) if i["type"] == "file"]
        return self._dirs[k]

    def _tree(self, repo: str, ref: str) -> list[TreeEntry]:
        k = (repo, ref)
        if k not in self._trees:
            payload = self._get_json(
                f"{self.github_api}/repos/{repo}/git/trees/{ref}", {"recursive": 1}
            )
            if payload["truncated"]:
                raise ValueError(f"GitHub truncated the tree of {repo}@{ref}")
            entries = cast(list[TreeEntry], payload["tree"])
            self._trees[k] = [e for e in entries if e["type"] == "blob"]
        return self._trees[k]

    def _drop_units(self, fetch: DropFolder) -> list[Unit]:
        base = self.drop / fetch.vendor if self.drop else None
        if base is None or not base.is_dir():
            return []
        units: list[Unit] = []
        for path in sorted(base.rglob("*")):
            if path.is_file():
                key = path.relative_to(base).as_posix()
                units.append(
                    Unit(key, f"{fetch.url_prefix}{key}", _file_sha256(path), path.stat().st_size)
                )
        return units

    def units(self, fetch: Fetch) -> list[Unit]:
        pattern = re.compile(fetch.match)
        match fetch:
            case ReleaseAssets(tag=tag, repo=repo):
                assets = self._release_assets(repo).get(tag, [])
                found = [
                    Unit(
                        a["name"],
                        a["browser_download_url"],
                        f"{a['updated_at']}:{a['size']}",
                        a["size"],
                    )
                    for a in assets
                ]
            case GitDir(repo=repo, path=path, ref=ref):
                found = [
                    Unit(i["name"], i["download_url"], i["sha"], i["size"])
                    for i in self._dir(repo, path, ref)
                ]
            case GitTree(repo=repo, ref=ref):
                found = [
                    Unit(e["path"], f"{fetch.url_prefix}{e['path']}", e["sha"], e["size"])
                    for e in self._tree(repo, ref)
                ]
            case Kaggle(owner=owner, slug=slug):
                k = (owner, slug)
                if k not in self._kaggle:
                    meta = cast(
                        KaggleDataset,
                        self._get_json(f"{self.kaggle_api}/datasets/view/{owner}/{slug}"),
                    )
                    self._kaggle[k] = Unit(
                        f"{slug}.zip",
                        f"{self.kaggle_api}/datasets/download/{owner}/{slug}",
                        f"v{meta['currentVersionNumber']}",
                        meta.get("totalBytes"),
                    )
                found = [self._kaggle[k]]
            case DropFolder():
                found = self._drop_units(fetch)
        return [u for u in found if pattern.fullmatch(u.key)]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def github_headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "nbalake"}
    if token := os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = f"Bearer {token}"
    return h


def make_client(timeout: float = 120.0) -> httpx.Client:
    return httpx.Client(follow_redirects=True, timeout=timeout, headers=github_headers())


@dataclass(slots=True)
class CaptureReport:
    fetched: list[FetchRecord]
    skipped: int
    failed: dict[str, str]

    @property
    def bytes(self) -> int:
        return sum(r.size for r in self.fetched)


ProgressFn = Callable[[Unit, int, int | None, bool], None]


def plan(datasets: Iterable[Dataset], index: Index, store: RawStore) -> tuple[list[Unit], int]:
    have = store.versions()
    wanted: dict[str, Unit] = {}
    for ds in datasets:
        for u in index.units(ds.fetch):
            wanted.setdefault(u.url, u)
    todo = [u for u in wanted.values() if (u.url, u.version) not in have]
    return todo, len(wanted) - len(todo)


def _read_drop(root: Root, unit: Unit, progress: ProgressFn | None) -> Iterator[bytes]:
    path = root.drop / unit.url.removeprefix("drop://")
    done = 0
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            done += len(chunk)
            if progress:
                progress(unit, done, unit.size, False)
            yield chunk
    if progress:
        progress(unit, done, unit.size, True)


def _stream(client: httpx.Client, unit: Unit, progress: ProgressFn | None) -> Iterator[bytes]:
    with client.stream("GET", unit.url) as r:
        r.raise_for_status()
        total = int(r.headers["content-length"]) if "content-length" in r.headers else unit.size
        done = 0
        for chunk in r.iter_bytes(CHUNK):
            done += len(chunk)
            if progress:
                progress(unit, done, total, False)
            yield chunk
    if progress:
        progress(unit, done, total, True)


def capture(
    root: Root,
    datasets: Iterable[Dataset],
    *,
    concurrency: int = 8,
    limit: int | None = None,
    progress: ProgressFn | None = None,
    client: httpx.Client | None = None,
    index: Index | None = None,
) -> CaptureReport:
    store = RawStore(root)
    own = client is None
    client = client or make_client()
    try:
        idx = index or Index(client, drop=root.drop)
        todo, skipped = plan(datasets, idx, store)
        if limit is not None:
            todo = todo[:limit]
        fetched: list[FetchRecord] = []
        failed: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(
                    store.put,
                    u,
                    _read_drop(root, u, progress)
                    if u.url.startswith("drop://")
                    else _stream(client, u, progress),
                ): u
                for u in todo
            }
            for fut in as_completed(futures):
                unit = futures[fut]
                try:
                    fetched.append(fut.result())
                except Exception as e:
                    failed[unit.url] = f"{type(e).__name__}: {e}"
        return CaptureReport(fetched=fetched, skipped=skipped, failed=failed)
    finally:
        if own:
            client.close()


def units_in_store(ds: Dataset, records: list[FetchRecord]) -> list[FetchRecord]:
    """Latest capture per unit key for this dataset (every capture when versions=ALL)."""
    pattern = re.compile(ds.fetch.match)
    mine = [r for r in records if ds.fetch.claims(r.url) and pattern.fullmatch(r.key)]

    if ds.versions is Versions.ALL:
        return sorted(mine, key=lambda r: (r.key, r.fetched_at))
    latest: dict[str, FetchRecord] = {}
    for r in sorted(mine, key=lambda r: r.fetched_at):
        latest[r.key] = r
    return sorted(latest.values(), key=lambda r: r.key)


def missing_dates(ds: Dataset, records: list[FetchRecord], through: date) -> list[date]:
    """UTC dates from the dataset's first capture through `through` with no capture of it."""
    captured = {date.fromisoformat(r.fetched_at[:10]) for r in units_in_store(ds, records)}
    if not captured:
        return []
    first = min(captured)
    days = (first + timedelta(days=n) for n in range((through - first).days + 1))
    return [d for d in days if d not in captured]


def blob_path(root: Root, rec: FetchRecord) -> Path:
    return root.blob(rec.sha256)
