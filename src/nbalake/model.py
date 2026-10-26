from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

SDV_REPO = "sportsdataverse/sportsdataverse-data"


@dataclass(frozen=True, slots=True)
class Unit:
    key: str
    url: str
    version: str
    size: int | None


@dataclass(frozen=True, slots=True)
class ReleaseAssets:
    tag: str
    match: str
    repo: str = SDV_REPO

    @property
    def url_prefix(self) -> str:
        return f"https://github.com/{self.repo}/releases/download/{self.tag}/"

    def claims(self, url: str) -> bool:
        return url.startswith(self.url_prefix)


@dataclass(frozen=True, slots=True)
class GitDir:
    repo: str
    path: str
    match: str
    ref: str = "main"

    @property
    def url_prefix(self) -> str:
        return f"https://raw.githubusercontent.com/{self.repo}/{self.ref}/{self.path}/"

    def claims(self, url: str) -> bool:
        return url.startswith(self.url_prefix)


@dataclass(frozen=True, slots=True)
class GitTree:
    """Every file in a repository whose full path matches, listed in one recursive tree call."""

    repo: str
    match: str
    ref: str = "main"

    @property
    def url_prefix(self) -> str:
        return f"https://raw.githubusercontent.com/{self.repo}/{self.ref}/"

    def claims(self, url: str) -> bool:
        return url.startswith(self.url_prefix)


@dataclass(frozen=True, slots=True)
class Kaggle:
    owner: str
    slug: str
    match: str = r".+\.zip"

    @property
    def url_prefix(self) -> str:
        return f"https://www.kaggle.com/api/v1/datasets/download/{self.owner}/{self.slug}"

    def claims(self, url: str) -> bool:
        return url.partition("?")[0] == self.url_prefix


@dataclass(frozen=True, slots=True)
class DropFolder:
    """Files the owner downloaded by hand into <root>/drop/<vendor>/, keyed by relative path."""

    vendor: str
    match: str

    @property
    def url_prefix(self) -> str:
        return f"drop://{self.vendor}/"

    def claims(self, url: str) -> bool:
        return url.startswith(self.url_prefix)


Fetch = ReleaseAssets | GitDir | GitTree | Kaggle | DropFolder


@dataclass(frozen=True, slots=True)
class Parquet:
    pass


@dataclass(frozen=True, slots=True)
class Csv:
    member: str | None = None
    nulls: tuple[str, ...] = ("",)
    all_varchar: bool = False


Parse = Parquet | Csv


class License(Enum):
    OPEN = "open"
    PERSONAL = "personal"


class Versions(Enum):
    LATEST = "latest"
    ALL = "all"


def digits_to_int(groups: dict[str, str]) -> dict[str, object]:
    return {k: int(v) if v.isdigit() else v for k, v in groups.items()}


@dataclass(frozen=True, slots=True)
class Dataset:
    name: str
    fetch: Fetch
    parse: Parse = field(default_factory=Parquet)
    partition: str | None = None
    sort: tuple[str, ...] = ()
    versions: Versions = Versions.LATEST
    types: tuple[tuple[str, str], ...] = ()
    unit_columns: Callable[[dict[str, str]], dict[str, object]] = digits_to_int
    description: str = ""
    license: License = License.OPEN

    def __post_init__(self) -> None:
        schema, _, table = self.name.partition(".")
        if not schema or not table or "." in table:
            raise ValueError(f"dataset name must be <schema>.<table>: {self.name!r}")
        re.compile(self.fetch.match)

    @property
    def schema(self) -> str:
        return self.name.partition(".")[0]

    @property
    def table(self) -> str:
        return self.name.partition(".")[2]

    @property
    def qualified(self) -> str:
        return f'lake."{self.schema}"."{self.table}"'

    def groups(self, key: str) -> dict[str, str] | None:
        m = re.fullmatch(self.fetch.match, key)
        return m.groupdict() if m else None

    def columns_for(self, key: str) -> dict[str, object]:
        groups = self.groups(key)
        if groups is None:
            raise ValueError(f"{key!r} does not match {self.name}")
        return self.unit_columns(groups)
