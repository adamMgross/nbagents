"""The report spec an agent writes, parsed into named types."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, cast

CONTEXT_FILE = Path(__file__).parent / "context.toml"
MAX_TILES = 4
MAX_PANELS = 24
MAX_NAME_WORDS = 5
ARTIFACT_PREFIX = "https://claude.ai/"


class SpecError(ValueError):
    pass


class Format(StrEnum):
    TEXT = "text"
    INT = "int"
    NUM1 = "num1"
    NUM2 = "num2"
    NUM3 = "num3"
    SIGNED1 = "signed1"
    SIGNED2 = "signed2"
    PCT1 = "pct1"
    RATE3 = "rate3"
    SEASON = "season"
    DATE = "date"


class Kind(StrEnum):
    SOURCE = "source"
    METRIC = "metric"
    STAT = "stat"


@dataclass(frozen=True, slots=True)
class Link:
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class Entry:
    key: str
    kind: Kind
    title: str
    text: str
    links: tuple[Link, ...]


@dataclass(frozen=True, slots=True)
class Tile:
    label: str
    value: str
    note: str


@dataclass(frozen=True, slots=True)
class Column:
    key: str
    label: str
    format: Format
    bar: bool


@dataclass(frozen=True, slots=True)
class Line:
    type: ClassVar[str] = "line"
    title: str
    caption: str
    sql: str
    x: str
    y: str
    x_format: Format
    y_format: Format
    y_unit: str
    baseline: str


@dataclass(frozen=True, slots=True)
class Bar:
    type: ClassVar[str] = "bar"
    title: str
    caption: str
    sql: str
    label: str
    value: str
    value_format: Format
    value_unit: str


@dataclass(frozen=True, slots=True)
class Scatter:
    type: ClassVar[str] = "scatter"
    title: str
    caption: str
    sql: str
    x: str
    y: str
    label: str
    x_format: Format
    y_format: Format
    x_unit: str
    y_unit: str


@dataclass(frozen=True, slots=True)
class Multiples:
    type: ClassVar[str] = "multiples"
    title: str
    caption: str
    sql: str
    facet: str
    x: str
    y: str
    x_format: Format
    y_format: Format
    y_unit: str
    baseline: str


@dataclass(frozen=True, slots=True)
class Table:
    type: ClassVar[str] = "table"
    title: str
    caption: str
    sql: str
    columns: tuple[Column, ...]
    search: str | None
    decades: str | None


@dataclass(frozen=True, slots=True)
class Text:
    type: ClassVar[str] = "text"
    title: str
    body: str


Chart = Line | Bar | Scatter | Multiples
Block = Chart | Table | Text
BLOCK_TYPES = tuple(t.type for t in (Line, Bar, Scatter, Multiples, Table, Text))


@dataclass(frozen=True, slots=True)
class Step:
    step: str
    text: str


@dataclass(frozen=True, slots=True)
class Term:
    term: str
    definition: str


@dataclass(frozen=True, slots=True)
class Glossary:
    intro: str | None
    terms: tuple[Term, ...]


@dataclass(frozen=True, slots=True)
class Report:
    name: str
    title: str
    finding: str
    seasons: str | None
    tiles: tuple[Tile, ...]
    glossary: Glossary | None
    blocks: tuple[Block, ...]
    why: str
    method: tuple[Step, ...]
    context: tuple[Entry, ...]
    reading: tuple[Link, ...]
    artifact: str | None


class _Fields:
    """Reads one JSON object, naming its path in every error and rejecting unknown keys."""

    def __init__(self, raw: Any, path: str) -> None:
        if not isinstance(raw, Mapping):
            raise SpecError(f"{path} must be an object")
        self.raw = cast(Mapping[str, Any], raw)
        self.path, self.seen = path, set[str]()

    def text(self, key: str, *, required: bool = True) -> str:
        self.seen.add(key)
        value = self.raw.get(key, "")
        if not isinstance(value, str) or (required and not value.strip()):
            raise SpecError(f"{self.path}.{key} must be non-empty text")
        return value.strip()

    def optional(self, key: str) -> str | None:
        return self.text(key, required=False) or None

    def flag(self, key: str) -> bool:
        self.seen.add(key)
        value = self.raw.get(key, False)
        if not isinstance(value, bool):
            raise SpecError(f"{self.path}.{key} must be true or false")
        return value

    def format(self, key: str) -> Format:
        value = self.text(key)
        try:
            return Format(value)
        except ValueError:
            raise SpecError(
                f"{self.path}.{key} is {value!r}, not one of {', '.join(Format)}"
            ) from None

    def items(self, key: str, *, required: bool = True) -> list[tuple[Any, str]]:
        self.seen.add(key)
        value = self.raw.get(key, [])
        if not isinstance(value, list) or (required and not value):
            raise SpecError(f"{self.path}.{key} must be a non-empty list")
        return [(v, f"{self.path}.{key}[{i}]") for i, v in enumerate(cast(list[Any], value))]

    def done(self) -> None:
        if extra := sorted(set(self.raw) - self.seen):
            raise SpecError(f"{self.path} has unknown fields: {', '.join(extra)}")


def _link(raw: Any, path: str) -> Link:
    f = _Fields(raw, path)
    link = Link(f.text("title"), f.text("url"))
    f.done()
    if not link.url.startswith("https://"):
        raise SpecError(f"{path}.url must be a public https link, not {link.url!r}")
    return link


def _glossary(raw: Any, path: str) -> Glossary:
    f = _Fields(raw, path)
    terms: list[Term] = []
    for t, term_path in f.items("terms"):
        tf = _Fields(t, term_path)
        terms.append(Term(tf.text("term"), tf.text("definition")))
        tf.done()
    glossary = Glossary(f.optional("intro"), tuple(terms))
    f.done()
    return glossary


def _block(raw: Any, path: str) -> Block:
    f = _Fields(raw, path)
    kind = f.text("type")
    block: Block
    match kind:
        case "line":
            block = Line(
                f.text("title"),
                f.text("caption", required=False),
                f.text("sql"),
                f.text("x"),
                f.text("y"),
                f.format("x_format"),
                f.format("y_format"),
                f.text("y_unit", required=False),
                f.text("baseline", required=False),
            )
        case "table":
            columns: list[Column] = []
            for c, cpath in f.items("columns"):
                cf = _Fields(c, cpath)
                columns.append(
                    Column(cf.text("key"), cf.text("label"), cf.format("format"), cf.flag("bar"))
                )
                cf.done()
            block = Table(
                f.text("title"),
                f.text("caption", required=False),
                f.text("sql"),
                tuple(columns),
                f.optional("search"),
                f.optional("decades"),
            )
        case "bar":
            block = Bar(
                f.text("title"),
                f.text("caption", required=False),
                f.text("sql"),
                f.text("label"),
                f.text("value"),
                f.format("value_format"),
                f.text("value_unit", required=False),
            )
        case "scatter":
            block = Scatter(
                f.text("title"),
                f.text("caption", required=False),
                f.text("sql"),
                f.text("x"),
                f.text("y"),
                f.text("label"),
                f.format("x_format"),
                f.format("y_format"),
                f.text("x_unit", required=False),
                f.text("y_unit", required=False),
            )
        case "multiples":
            block = Multiples(
                f.text("title"),
                f.text("caption", required=False),
                f.text("sql"),
                f.text("facet"),
                f.text("x"),
                f.text("y"),
                f.format("x_format"),
                f.format("y_format"),
                f.text("y_unit", required=False),
                f.text("baseline", required=False),
            )
        case "text":
            block = Text(f.text("title"), f.text("body"))
        case _:
            raise SpecError(f"{path}.type is {kind!r}, not one of {', '.join(BLOCK_TYPES)}")
    f.done()
    return block


def parse(raw: Any, context: Mapping[str, Entry]) -> Report:
    f = _Fields(raw, "spec")
    tiles: list[Tile] = []
    for t, path in f.items("tiles", required=False):
        tf = _Fields(t, path)
        tiles.append(Tile(tf.text("label"), tf.text("value"), tf.text("note", required=False)))
        tf.done()
    if len(tiles) > MAX_TILES:
        raise SpecError(f"spec.tiles has {len(tiles)}, at most {MAX_TILES} tiles fit")
    method: list[Step] = []
    for s, path in f.items("method"):
        sf = _Fields(s, path)
        method.append(Step(sf.text("step"), sf.text("text")))
        sf.done()
    f.seen.add("glossary")
    glossary = _glossary(f.raw["glossary"], "spec.glossary") if "glossary" in f.raw else None
    entries: list[Entry] = []
    for key, path in f.items("context"):
        if key not in context:
            raise SpecError(f"{path} is {key!r}, which src/nbalake/report/context.toml lacks")
        entries.append(context[key])
    report = Report(
        name=f.text("name"),
        title=f.text("title"),
        finding=f.text("finding"),
        seasons=f.optional("seasons"),
        tiles=tuple(tiles),
        glossary=glossary,
        blocks=tuple(_block(b, path) for b, path in f.items("blocks")),
        why=f.text("why"),
        method=tuple(method),
        context=tuple(entries),
        reading=tuple(_link(r, path) for r, path in f.items("reading", required=False)),
        artifact=f.optional("artifact"),
    )
    f.done()
    if len(report.name.split()) > MAX_NAME_WORDS:
        raise SpecError(f"spec.name is the page's short name, at most {MAX_NAME_WORDS} words")
    if report.artifact and not report.artifact.startswith(ARTIFACT_PREFIX):
        raise SpecError(f"spec.artifact must be a {ARTIFACT_PREFIX} artifact link")
    return report


def load_context(path: Path = CONTEXT_FILE) -> dict[str, Entry]:
    found: dict[str, Entry] = {}
    for key, raw in tomllib.loads(path.read_text(encoding="utf-8")).items():
        f = _Fields(raw, f"context.{key}")
        found[key] = Entry(
            key,
            Kind(f.text("kind")),
            f.text("title"),
            " ".join(f.text("text").split()),
            tuple(_link(link, path) for link, path in f.items("links", required=False)),
        )
        f.done()
    return found
