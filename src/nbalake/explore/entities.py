from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

import duckdb

FUZZY_THRESHOLD = 0.9
KEY_SQL = (
    "trim(regexp_replace(regexp_replace(lower(strip_accents({x})), '[''.]', '', 'g'), "
    "'[^a-z0-9]+', ' ', 'g'))"
)


class EntityKind(Enum):
    PLAYER = "player"
    TEAM = "team"
    GAME = "game"


class Tier(Enum):
    EXACT = 1
    ALIAS = 2
    TOKENS = 3
    PREFIX = 4
    FUZZY = 5


@dataclass(frozen=True, slots=True)
class Entity:
    kind: EntityKind
    id: str
    label: str
    key: str
    aliases: tuple[str, ...]
    season_min: int | None
    season_max: int | None
    context: str
    similarity: float


@dataclass(frozen=True, slots=True)
class Match:
    query: str
    tier: Tier | None
    candidates: tuple[Entity, ...]

    @property
    def resolved(self) -> Entity | None:
        ids = {c.id for c in self.candidates}
        return self.candidates[0] if len(ids) == 1 else None


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"['.]", "", stripped)).strip()


def tier(entity: Entity, key: str) -> Tier | None:
    tokens = key.split()
    names = (entity.key, *entity.aliases)
    name_tokens = {t for n in names for t in n.split()}
    if entity.key == key:
        return Tier.EXACT
    if key in entity.aliases:
        return Tier.ALIAS
    if set(tokens) <= name_tokens:
        return Tier.TOKENS
    if all(any(n.startswith(t) for n in name_tokens) for t in tokens):
        return Tier.PREFIX
    if entity.similarity >= FUZZY_THRESHOLD:
        return Tier.FUZZY
    return None


def _rank(e: Entity, tokens: set[str]) -> tuple[int, float, str]:
    unmatched = len(set(e.key.split()) - tokens)
    match e.kind:
        case EntityKind.GAME:
            return (unmatched, 0.0, e.label)
        case EntityKind.PLAYER | EntityKind.TEAM:
            span = (e.season_max or 0) - (e.season_min or 0)
            return (unmatched, -span - e.similarity, e.label)


def resolve(candidates: Sequence[Entity], text: str) -> Match:
    key = normalize(text)
    tiered = [(t, e) for e in candidates if (t := tier(e, key)) is not None]
    if not tiered:
        return Match(text, None, ())
    best = min(t.value for t, _ in tiered)
    tokens = set(key.split())
    chosen = sorted((e for t, e in tiered if t.value == best), key=lambda e: _rank(e, tokens))
    return Match(text, Tier(best), tuple(chosen))


def candidates(con: duckdb.DuckDBPyConnection, kind: EntityKind, text: str) -> list[Entity]:
    key = normalize(text)
    longest = max(key.split(), key=len, default="")
    rows = con.execute(
        """
        SELECT kind, id, label, key, aliases, season_min, season_max, context,
               jaro_winkler_similarity(key, $key) AS similarity
        FROM nba.entity_index
        WHERE kind = $kind
          AND (jaro_winkler_similarity(key, $key) >= 0.8
               OR contains(key || ' ' || array_to_string(aliases, ' '), $longest))
        """,
        {"key": key, "longest": longest, "kind": kind.value},
    ).fetchall()
    return [
        Entity(EntityKind(k), i, label, ek, tuple(a), lo, hi, ctx or "", float(sim))
        for k, i, label, ek, a, lo, hi, ctx, sim in rows
    ]


def find(con: duckdb.DuckDBPyConnection, kind: EntityKind, text: str) -> Match:
    return resolve(candidates(con, kind, text), text)
