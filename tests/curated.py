from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from pathlib import Path

import duckdb
import pyarrow as pa

from nbalake.curate import Gate, Step, build, shipped_gates, shipped_steps
from nbalake.datasets import SCHEMAS
from nbalake.explore.query import explain
from nbalake.lake import Root, connect, transaction
from nbalake.models import ALL, Model

UNIQUE_GATE = "games_game_id_unique"
SCORES_GATE = "games_scores_agree_with_team_box"
TRACER_SQL = """
SELECT
    season::INTEGER AS season, season_type, game_id, CAST(game_date AS DATE) AS game_date,
    home_team_id, home_team_abbreviation AS home_abbr,
    away_team_id, away_team_abbreviation AS away_abbr, home_pts, away_pts,
    CASE WHEN home_pts > away_pts THEN home_team_id
         WHEN away_pts > home_pts THEN away_team_id END AS winner_team_id
FROM sdv.nba_stats_schedules
"""
STEPS = (Step(Model("games", partition="season", sort=("game_date", "game_id")), TRACER_SQL),)
GATES = (
    Gate(
        UNIQUE_GATE,
        "SELECT game_id, count(*) AS n FROM nba.games GROUP BY game_id HAVING count(*) > 1",
    ),
    Gate(
        SCORES_GATE,
        """
        SELECT g.game_id, g.home_pts, g.away_pts,
               hb.points AS home_box_pts, ab.points AS away_box_pts
        FROM nba.games g
        JOIN sdv.nba_stats_team_boxscores hb
          ON hb.game_id = g.game_id AND hb.team_id = g.home_team_id
        JOIN sdv.nba_stats_team_boxscores ab
          ON ab.game_id = g.game_id AND ab.team_id = g.away_team_id
        WHERE g.home_pts <> hb.points OR g.away_pts <> ab.points
        """,
    ),
)
STAGED: dict[str, list[list[str]]] = json.loads(
    (Path(__file__).parent / "fixtures" / "staged_schema.json").read_text(encoding="utf-8")
)


STAGED_REF = re.compile(rf"\b((?:{'|'.join(SCHEMAS)})\.\w+)")


def sources(*names: str, gate_prefix: str | None = None) -> tuple[str, ...]:
    sql = [s.sql for s in shipped_steps(models(*names))]
    if gate_prefix:
        sql += [g.sql for g in shipped_gates(gate_prefix)]
    return tuple(sorted({m for text in sql for m in STAGED_REF.findall(text)} & STAGED.keys()))


def empty_lake(root: Root, tables: Iterable[str] | None = None) -> duckdb.DuckDBPyConnection:
    names = sorted(STAGED if tables is None else tables)
    schemas = tuple(sorted({t.split(".", 1)[0] for t in names} | {"nba"}))
    con = connect(root, schemas=schemas)
    with transaction(con):
        for table in names:
            cols = ", ".join(f'"{c}" {kind}' for c, kind in STAGED[table])
            con.execute(f"CREATE TABLE {table} ({cols})")
    return con


def insert(con: duckdb.DuckDBPyConnection, table: str, rows: Sequence[dict]) -> None:
    keys = list(dict.fromkeys(k for row in rows for k in row))
    con.register("_rows", pa.Table.from_pylist([{k: row.get(k) for k in keys} for row in rows]))
    con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM _rows")
    con.unregister("_rows")


def models(*names: str) -> tuple[Model, ...]:
    by_name = {m.name: m for m in ALL}
    return tuple(by_name[n] for n in names)


def build_models(con: duckdb.DuckDBPyConnection, *names: str) -> dict[str, int | None]:
    steps: tuple[Step, ...] = shipped_steps(models(*names))
    with transaction(con):
        return {s.model.name: build(con, s) for s in steps}


def rows(con: duckdb.DuckDBPyConnection, sql: str, params: Sequence[object] = ()) -> list[tuple]:
    return con.execute(sql, list(params)).fetchall()


def gate(name: str):
    return next(g for g in shipped_gates() if g.name == name)


def files_read(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    explained = explain(con, sql, timeout=600)
    assert any(s.files is not None for s in explained.scans), explained.plan
    return explained.files_read


def table_rows_equal_its_sql(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    """The chunked table holds exactly what its SQL returns when run whole."""
    (sql,) = [s.sql for s in shipped_steps(models(name))]
    every = f"SELECT * FROM nba.{name} ORDER BY ALL"
    whole = f"SELECT * FROM ({sql}) ORDER BY ALL"
    return con.execute(every).fetchall() == con.execute(whole).fetchall()
