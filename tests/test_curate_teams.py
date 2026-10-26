from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

import nbalake
from nbalake.curate import check
from nbalake.lake import Root
from tests.curated import build_models, empty_lake, gate, insert, rows

SEED = Path(nbalake.__file__).parent / "sql" / "seed" / "franchises.csv"
TABLES = (
    "bref.team_summaries",
    "fte.elo",
    "sdv.nba_team_crosswalk",
    "sdv.nba_team_group_seasons",
    "sdv.nba_stats_schedules",
    "sdv.nba_stats_team_boxscores",
)
LAKERS, CHARLOTTE, PELICANS, SUNS = 1610612747, 1610612766, 1610612740, 1610612756


def bref(season: int, team: str, abbreviation: str, lg: str = "NBA", w: int = 41) -> dict:
    return {"season": season, "lg": lg, "team": team, "abbreviation": abbreviation, "w": w}


def group(season: int, espn_id: int, name: str, notes: str, conference: str = "west") -> dict:
    return {
        "league": "nba",
        "season": season,
        "team_id": str(espn_id),
        "team_name": name,
        "conference_id": f"nba:{conference}",
        "division_id": "nba:pacific",
        "notes": notes,
    }


@pytest.fixture
def con(root: Root) -> Iterator[duckdb.DuckDBPyConnection]:
    con = empty_lake(root, TABLES)
    yield con
    con.close()


def seed_rows() -> list[dict[str, str]]:
    with SEED.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_franchise_seed_maps_the_thirty_nba_ids_and_numbers_defunct_franchises_densely() -> None:
    seed = seed_rows()
    ids = {int(r["team_id"]) for r in seed}
    current = {i for i in ids if i < 800000000 or i >= 900000000}
    defunct = sorted(i for i in ids if 800000000 < i < 900000000)

    assert len({r["code"] for r in seed}) == len(seed)
    assert current == set(range(1610612737, 1610612767))
    assert defunct == list(range(800000001, 800000001 + len(defunct)))
    assert all(len({r["franchise"] for r in seed if int(r["team_id"]) == i}) == 1 for i in ids)


@pytest.mark.parametrize(
    ("codes", "team_id"),
    [
        (("MNL", "LAL"), LAKERS),
        (("SEA", "OKC"), 1610612760),
        (("CHH", "CHA", "CHO"), CHARLOTTE),
        (("NOH", "NOK", "NOP"), PELICANS),
        (("BAL", "CAP", "WSB", "WAS"), 1610612764),
        (("NJA", "NYA", "NYN", "NJN", "BRK"), 1610612751),
        (("DLC", "TEX", "SAA", "SAS"), 1610612759),
    ],
)
def test_relocations_and_renames_keep_one_team_id(codes: tuple[str, ...], team_id: int) -> None:
    by_code = {r["code"]: int(r["team_id"]) for r in seed_rows()}

    assert {by_code[c] for c in codes} == {team_id}


def test_the_original_baltimore_bullets_are_not_the_wizards() -> None:
    by_code = {r["code"]: int(r["team_id"]) for r in seed_rows()}

    assert by_code["BLB"] != by_code["BAL"]
    assert 800000000 < by_code["BLB"] < 900000000


def test_relocated_franchise_is_one_team_spanning_both_cities(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "bref.team_summaries",
        [bref(1960, "Minneapolis Lakers", "MNL"), bref(1961, "Los Angeles Lakers", "LAL")],
    )

    built = build_models(con, "franchises", "team_seasons", "teams")

    assert built["team_seasons"] == 2
    assert rows(con, "SELECT season, abbreviation, name FROM nba.team_seasons ORDER BY 1") == [
        (1960, "MNL", "Minneapolis Lakers"),
        (1961, "LAL", "Los Angeles Lakers"),
    ]
    assert rows(con, "SELECT * FROM nba.teams") == [
        (LAKERS, "Los Angeles Lakers", "LAL", None, 1960, 1961, True, None, "NBA")
    ]


def test_one_season_merges_bref_crosswalk_groups_and_nba_tricode_into_one_row(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(con, "bref.team_summaries", [bref(2016, "Phoenix Suns", "PHO", w=23)])
    insert(
        con,
        "sdv.nba_team_crosswalk",
        [
            {
                "season": 2016,
                "espn_team_id": 21,
                "nba_team_id": str(SUNS),
                "nba_team_city": "Phoenix",
                "nba_team_name": "Phoenix Suns",
            }
        ],
    )
    insert(
        con,
        "sdv.nba_team_group_seasons",
        [group(2016, 21, "Phoenix Suns", f"nba_stats_team_id={SUNS}")],
    )
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            {
                "season": 2016,
                "home_team_id": SUNS,
                "home_team_abbreviation": "PHX",
                "away_team_id": 1610616857,
                "away_team_abbreviation": "TMM",
            }
        ],
    )

    build_models(con, "franchises", "team_seasons")

    assert rows(
        con,
        "SELECT season, team_id, abbreviation, bref_abbr, name, city, conference, espn_team_id, w "
        "FROM nba.team_seasons",
    ) == [(2016, SUNS, "PHX", "PHO", "Phoenix Suns", "Phoenix", "west", 21, 23)]


def test_current_season_without_bref_carries_the_last_known_tricode_forward(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_stats_schedules",
        [
            {
                "season": 2026,
                "home_team_id": SUNS,
                "home_team_abbreviation": "PHX",
                "away_team_id": LAKERS,
                "away_team_abbreviation": "LAL",
            }
        ],
    )
    insert(
        con,
        "sdv.nba_team_group_seasons",
        [group(2027, 21, "Phoenix Suns", f"nba_stats_team_id={SUNS}")],
    )

    build_models(con, "franchises", "team_seasons", "teams")

    assert rows(
        con, "SELECT season, abbreviation, name FROM nba.team_seasons WHERE team_id = ?", [SUNS]
    ) == [
        (2026, "PHX", None),
        (2027, "PHX", "Phoenix Suns"),
    ]
    assert dict(rows(con, "SELECT team_id, active FROM nba.teams")) == {SUNS: True, LAKERS: True}


def test_pre_1997_espn_keyed_groups_map_through_the_earliest_crosswalk_season(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "sdv.nba_team_crosswalk",
        [
            {"season": 2002, "espn_team_id": 3, "nba_team_id": str(CHARLOTTE)},
            {"season": 2003, "espn_team_id": 3, "nba_team_id": str(PELICANS)},
        ],
    )
    insert(
        con, "sdv.nba_team_group_seasons", [group(1990, 3, "Charlotte Hornets", "abbr=CHH", "east")]
    )

    build_models(con, "franchises", "team_seasons")

    assert rows(con, "SELECT team_id, conference FROM nba.team_seasons WHERE season = 1990") == [
        (CHARLOTTE, "east")
    ]


def test_teams_gates_pass_on_mapped_codes_and_flag_unmapped_ones(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "bref.team_summaries",
        [bref(1990, "Charlotte Hornets", "CHH"), {"season": 1990, "team": "League Average"}],
    )
    insert(con, "fte.elo", [{"team_id": "CHH"}])
    insert(
        con,
        "sdv.nba_stats_team_boxscores",
        [{"season": 1990, "team_id": CHARLOTTE}, {"season": 2013, "team_id": 0}],
    )
    build_models(con, "franchises", "team_seasons", "teams")
    names = (
        "teams_team_id_unique",
        "teams_franchise_code_unique",
        "teams_team_seasons_key_unique",
        "teams_every_source_code_maps",
        "teams_box_teams_have_a_season",
    )

    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)

    insert(con, "fte.elo", [{"team_id": "XYZ"}])
    insert(con, "sdv.nba_stats_team_boxscores", [{"season": 1991, "team_id": CHARLOTTE}])

    unmapped = check(con, gate("teams_every_source_code_maps"))
    missing = check(con, gate("teams_box_teams_have_a_season"))
    assert unmapped.sample == [{"source": "fte", "code": "XYZ"}]
    assert missing.sample == [{"season": 1991, "team_id": CHARLOTTE}]
