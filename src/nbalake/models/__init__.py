"""Curated models in build order. Each group module owns its models, SQL, and gates."""

from nbalake.models import (
    boxes,
    events,
    games,
    odds,
    officiating,
    players,
    search,
    seasons,
    teams,
)
from nbalake.models.model import Chunk, Kind, Model

GROUPS = (teams, players, games, boxes, events, seasons, officiating, odds, search)

ALL: tuple[Model, ...] = tuple(m for group in GROUPS for m in group.MODELS)

if len({m.name for m in ALL}) != len(ALL):
    raise RuntimeError("duplicate curated model names")

__all__ = ["ALL", "GROUPS", "Chunk", "Kind", "Model"]
