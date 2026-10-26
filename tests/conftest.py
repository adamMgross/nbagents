from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import tarfile
import threading
import zipfile
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from nbalake.capture import Index
from nbalake.lake import Root, connect
from nbalake.model import Dataset, ReleaseAssets

GITHUB_API = "https://api.github.com"
KAGGLE_API = "https://www.kaggle.com/api/v1"
KAGGLE_STORAGE = "https://storage.googleapis.com/kaggle-data-sets"

RELEASES = re.compile(r"^/repos/([^/]+/[^/]+)/releases$")
CONTENTS = re.compile(r"^/repos/([^/]+/[^/]+)/contents/(.+)$")
TREES = re.compile(r"^/repos/([^/]+/[^/]+)/git/trees/([^/]+)$")
KAGGLE_VIEW = re.compile(r"^/api/v1/datasets/view/([^/]+)/([^/]+)$")
KAGGLE_DOWNLOAD = re.compile(r"^/api/v1/datasets/download/([^/]+)/([^/]+)$")


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


@dataclass(frozen=True, slots=True)
class Reply:
    status: int
    body: bytes
    content_type: str
    location: str | None = None


NOT_FOUND = Reply(404, b'{"message":"Not Found"}', "application/json; charset=utf-8")


def json_reply(obj: object) -> Reply:
    return Reply(200, json.dumps(obj).encode(), "application/json; charset=utf-8")


class ChunkedBody(httpx.SyncByteStream):
    def __init__(self, data: bytes, chunk_size: int, fail_after: int | None = None) -> None:
        self.data = data
        self.chunk_size = chunk_size
        self.fail_after = fail_after

    def __iter__(self) -> Iterator[bytes]:
        end = len(self.data) if self.fail_after is None else self.fail_after
        for i in range(0, end, self.chunk_size):
            yield self.data[i : min(i + self.chunk_size, end)]
        if self.fail_after is not None:
            raise httpx.ReadError("upstream closed the connection mid-body")


class FakeUpstream:
    """GitHub releases and contents, Kaggle view and download, and their download URLs."""

    chunk_size = 64 * 1024

    def __init__(self) -> None:
        self._releases: dict[str, dict[str, dict[str, dict]]] = {}
        self._padding: dict[str, int] = {}
        self._dirs: dict[tuple[str, str, str], dict[str, dict]] = {}
        self._trees: dict[tuple[str, str], dict[str, dict]] = {}
        self._truncated: set[tuple[str, str]] = set()
        self._kaggle: dict[tuple[str, str], tuple[bytes, int]] = {}
        self._files: dict[str, bytes] = {}
        self._fail: set[str] = set()
        self._lock = threading.Lock()
        self.requests: list[httpx.Request] = []
        self.request_log: list[str] = []
        self.transport = httpx.MockTransport(self._handle)
        self.client = httpx.Client(transport=self.transport, follow_redirects=True)

    @property
    def index(self) -> Index:
        return Index(self.client)

    def close(self) -> None:
        self.client.close()

    def add_release(self, repo: str, tag: str) -> None:
        self._releases.setdefault(repo, {}).setdefault(tag, {})

    def add_release_asset(
        self,
        repo: str,
        tag: str,
        name: str,
        data: bytes,
        updated_at: str = "2026-10-01T00:00:00Z",
    ) -> str:
        url = f"https://github.com/{repo}/releases/download/{tag}/{name}"
        self.add_release(repo, tag)
        self._releases[repo][tag][name] = {
            "name": name,
            "size": len(data),
            "created_at": updated_at,
            "updated_at": updated_at,
            "browser_download_url": url,
            "content_type": "application/octet-stream",
            "state": "uploaded",
        }
        self._files[url] = data
        return url

    def pad_releases(self, repo: str, n: int) -> None:
        """Prepends n asset-less releases so the registered ones fall past page one."""
        self._releases.setdefault(repo, {})
        self._padding[repo] = n

    def add_git_file(
        self, repo: str, ref: str, path: str, name: str, data: bytes, sha: str | None = None
    ) -> str:
        url = f"https://raw.githubusercontent.com/{repo}/{ref}/{path}/{name}"
        self._dirs.setdefault((repo, ref, path), {})[name] = {
            "name": name,
            "path": f"{path}/{name}",
            "sha": sha or git_blob_sha(data),
            "size": len(data),
            "type": "file",
            "download_url": url,
            "url": f"{GITHUB_API}/repos/{repo}/contents/{path}/{name}?ref={ref}",
            "html_url": f"https://github.com/{repo}/blob/{ref}/{path}/{name}",
        }
        self._files[url] = data
        return url

    def add_git_dir(self, repo: str, ref: str, path: str, name: str) -> None:
        self._dirs.setdefault((repo, ref, path), {})[name] = {
            "name": name,
            "path": f"{path}/{name}",
            "sha": hashlib.sha1(name.encode()).hexdigest(),
            "size": 0,
            "type": "dir",
            "download_url": None,
            "url": f"{GITHUB_API}/repos/{repo}/contents/{path}/{name}?ref={ref}",
            "html_url": f"https://github.com/{repo}/tree/{ref}/{path}/{name}",
        }

    def add_git_tree_file(self, repo: str, ref: str, path: str, data: bytes) -> str:
        url = f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"
        sha = git_blob_sha(data)
        self._trees.setdefault((repo, ref), {})[path] = {
            "path": path,
            "mode": "100644",
            "type": "blob",
            "sha": sha,
            "size": len(data),
            "url": f"{GITHUB_API}/repos/{repo}/git/blobs/{sha}",
        }
        self._files[url] = data
        return url

    def add_git_tree_dir(self, repo: str, ref: str, path: str) -> None:
        self._trees.setdefault((repo, ref), {})[path] = {
            "path": path,
            "mode": "040000",
            "type": "tree",
            "sha": hashlib.sha1(path.encode()).hexdigest(),
            "url": f"{GITHUB_API}/repos/{repo}/git/trees/{path}",
        }

    def truncate_tree(self, repo: str, ref: str) -> None:
        self._truncated.add((repo, ref))

    def set_kaggle(self, owner: str, slug: str, data: bytes, version: int = 1) -> str:
        self._kaggle[(owner, slug)] = (data, version)
        self._files[self._kaggle_storage(owner, slug, version)] = data
        return f"{KAGGLE_API}/datasets/download/{owner}/{slug}"

    def fail_next(self, url: str) -> None:
        """The next GET of url (query ignored) sends half its body, then raises ReadError."""
        with self._lock:
            self._fail.add(url.split("?", 1)[0])

    def _kaggle_storage(self, owner: str, slug: str, version: int) -> str:
        return f"{KAGGLE_STORAGE}/{owner}/{slug}/v{version}/archive.zip"

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.request_log.append(str(request.url))
        bare = f"{request.url.scheme}://{request.url.host}{request.url.path}"
        with self._lock:
            failing = bare in self._fail
            self._fail.discard(bare)
        reply = self._route(request, bare)
        if failing and reply.location:
            with self._lock:
                self._fail.add(reply.location)
            failing = False
        headers = {"content-type": reply.content_type, "content-length": str(len(reply.body))}
        if reply.location:
            headers["location"] = reply.location
        fail_after = len(reply.body) // 2 if failing else None
        return httpx.Response(
            reply.status,
            headers=headers,
            stream=ChunkedBody(reply.body, self.chunk_size, fail_after),
        )

    def _route(self, request: httpx.Request, bare: str) -> Reply:
        host, path, params = request.url.host, request.url.path, request.url.params
        if host == "api.github.com":
            if m := RELEASES.match(path):
                return self._releases_reply(m[1], params)
            if m := CONTENTS.match(path):
                return self._contents_reply(m[1], params.get("ref", "main"), m[2].rstrip("/"))
            if (m := TREES.match(path)) and params.get("recursive") == "1":
                return self._tree_reply(m[1], m[2])
        elif host == "www.kaggle.com":
            if m := KAGGLE_VIEW.match(path):
                return self._kaggle_view_reply(m[1], m[2])
            if m := KAGGLE_DOWNLOAD.match(path):
                return self._kaggle_download_reply(m[1], m[2])
        if (data := self._files.get(bare)) is not None:
            return Reply(200, data, "application/octet-stream")
        return NOT_FOUND

    def _releases_reply(self, repo: str, params: httpx.QueryParams) -> Reply:
        if repo not in self._releases:
            return NOT_FOUND
        per_page = int(params.get("per_page", "30"))
        page = int(params.get("page", "1"))
        fillers = [
            {"tag_name": f"filler-{i}", "name": f"filler-{i}", "assets": []}
            for i in range(self._padding.get(repo, 0))
        ]
        real = [
            {
                "tag_name": tag,
                "name": tag,
                "draft": False,
                "prerelease": False,
                "assets": list(a.values()),
            }
            for tag, a in self._releases[repo].items()
        ]
        start = (page - 1) * per_page
        return json_reply((fillers + real)[start : start + per_page])

    def _contents_reply(self, repo: str, ref: str, path: str) -> Reply:
        entries = self._dirs.get((repo, ref, path))
        return NOT_FOUND if entries is None else json_reply(list(entries.values()))

    def _tree_reply(self, repo: str, ref: str) -> Reply:
        entries = self._trees.get((repo, ref))
        if entries is None:
            return NOT_FOUND
        truncated = (repo, ref) in self._truncated
        return json_reply({"sha": ref, "tree": list(entries.values()), "truncated": truncated})

    def _kaggle_view_reply(self, owner: str, slug: str) -> Reply:
        if (owner, slug) not in self._kaggle:
            return NOT_FOUND
        data, version = self._kaggle[(owner, slug)]
        return json_reply(
            {
                "ref": f"{owner}/{slug}",
                "title": slug,
                "currentVersionNumber": version,
                "totalBytes": len(data),
                "lastUpdated": "2026-10-01T00:00:00.000Z",
                "isPrivate": False,
            }
        )

    def _kaggle_download_reply(self, owner: str, slug: str) -> Reply:
        if (owner, slug) not in self._kaggle:
            return NOT_FOUND
        _, version = self._kaggle[(owner, slug)]
        location = self._kaggle_storage(owner, slug, version)
        return Reply(302, b"", "text/html; charset=utf-8", location=location)


@pytest.fixture
def root(tmp_path: Path) -> Root:
    return Root(tmp_path / "lake")


@pytest.fixture
def con(root: Root):
    con = connect(root, schemas=("t",))
    yield con
    con.close()


@pytest.fixture
def upstream() -> Iterator[FakeUpstream]:
    up = FakeUpstream()
    yield up
    up.close()


def dataset(**overrides: object) -> Dataset:
    fetch = overrides.pop("fetch", None) or ReleaseAssets(
        str(overrides.pop("tag", "tag")),
        str(overrides.pop("match", r"part_(?P<season>\d{4})\.parquet")),
        repo=str(overrides.pop("repo", "o/r")),
    )
    return Dataset(str(overrides.pop("name", "t.parts")), fetch, **overrides)  # type: ignore[arg-type]


def parquet_bytes(rows: list[dict] | pa.Table) -> bytes:
    table = rows if isinstance(rows, pa.Table) else pa.Table.from_pylist(rows)
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


def write_parquet(path: Path, rows: list[dict] | pa.Table) -> Path:
    path.write_bytes(parquet_bytes(rows))
    return path


def csv_bytes(header: Sequence[str], rows: Iterable[Sequence[object]]) -> bytes:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(header)
    for row in rows:
        w.writerow(["" if v is None else v for v in row])
    return out.getvalue().encode()


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> Path:
    path.write_bytes(csv_bytes(header, rows))
    return path


def zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def write_zip(path: Path, members: dict[str, bytes]) -> Path:
    path.write_bytes(zip_bytes(members))
    return path


def tar_xz_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as t:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def write_tar_xz(path: Path, members: dict[str, bytes]) -> Path:
    path.write_bytes(tar_xz_bytes(members))
    return path
