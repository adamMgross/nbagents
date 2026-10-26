from __future__ import annotations

from collections.abc import Iterator

import duckdb
import pytest

from nbalake.curate import check
from nbalake.lake import Root
from tests.curated import build_models, empty_lake, gate, insert, rows, sources

MODELS = (
    "franchises",
    "espn_bref_links",
    "player_xref",
    "players",
    "recorded_from",
    "player_seasons",
    "team_season_stats",
    "raptor",
    "awards",
)
CLE, LAL = 1610612739, 1610612747


def key(season: int, team: str, slug: str = "jamesle01", lg: str = "NBA") -> dict:
    return {"season": season, "lg": lg, "player_id": slug, "team": team}


@pytest.fixture
def con(root: Root) -> Iterator[duckdb.DuckDBPyConnection]:
    con = empty_lake(root, sources(*MODELS, gate_prefix="seasons_"))
    insert(
        con,
        "bref.player_career_info",
        [
            {"player_id": "jamesle01", "player": "LeBron James", "from": 2004, "to": 2026},
            {"player_id": "russebi01", "player": "Bill Russell", "from": 1957, "to": 1969},
        ],
    )
    yield con
    con.close()


def test_player_seasons_join_every_bref_table_on_the_team_season_and_mark_multi_team_rows(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "bref.player_totals",
        [
            {**key(2016, "CLE"), "g": 76, "pts": 1920, "orb": 111},
            {**key(2019, "2TM"), "g": 55, "pts": 1505, "orb": 57},
            {**key(2019, "LAL"), "g": 55, "pts": 1505, "orb": 57},
        ],
    )
    insert(con, "bref.player_advanced", [{**key(2016, "CLE"), "per": 27.5, "ws": 13.6}])
    insert(con, "bref.player_per_100", [{**key(2016, "CLE"), "o_rtg": 118.0}])
    insert(con, "bref.player_shooting", [{**key(2016, "CLE"), "avg_dist_fga": 10.4}])
    insert(con, "bref.player_play_by_play", [{**key(2016, "CLE"), "and1": 33}])
    insert(con, "bref.player_season_info", [{**key(2016, "CLE"), "experience": 13}])

    build_models(con, *MODELS)

    lebron = rows(con, "SELECT player_id FROM nba.player_xref WHERE source_id = 'jamesle01'")[0][0]
    assert rows(
        con,
        "SELECT season, player_id, team_id, multi_team, bref_team, g, pts, per, ws, o_rtg, "
        "avg_dist_fga, and1, experience FROM nba.player_seasons ORDER BY season, bref_team",
    ) == [
        (2016, lebron, CLE, False, "CLE", 76, 1920, 27.5, 13.6, 118.0, 10.4, 33, 13),
        (2019, lebron, None, True, "2TM", 55, 1505, None, None, None, None, None, None),
        (2019, lebron, LAL, False, "LAL", 55, 1505, None, None, None, None, None, None),
    ]


def test_a_stat_recorded_before_its_league_kept_it_fails_the_recording_gate(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(con, "bref.player_totals", [{**key(1960, "BOS", "russebi01"), "trb": 1778, "orb": None}])
    build_models(con, *MODELS)
    assert check(con, gate("seasons_no_stat_before_it_was_recorded")).violations == 0

    insert(
        con,
        "bref.player_totals",
        [
            {**key(1961, "BOS", "russebi01"), "orb": 0},
            {**key(1949, "BOS", "russebi01", lg="BAA"), "mp": 0},
        ],
    )
    build_models(con, *MODELS)

    flagged = check(con, gate("seasons_no_stat_before_it_was_recorded"))
    assert sorted((r["season"], r["stat"], r["first_season"]) for r in flagged.sample) == [
        (1949, "mp", None),
        (1961, "orb", 1974),
    ]


def test_raptor_unions_both_models_by_name_and_counts_unresolved_slugs(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "fte.raptor_player_modern",
        [
            {
                "player_id": "jamesle01",
                "player_name": "LeBron James",
                "season": 2016,
                "raptor_total": 7.9,
                "war_total": 15.2,
            }
        ],
    )
    insert(
        con,
        "fte.raptor_player_historical",
        [
            {
                "player_id": "jamesle01",
                "player_name": "LeBron James",
                "season": 2016,
                "raptor_total": 8.1,
            }
        ],
    )

    build_models(con, *MODELS)

    lebron = rows(con, "SELECT player_id FROM nba.player_xref WHERE source_id = 'jamesle01'")[0][0]
    assert rows(
        con, "SELECT model, player_id, raptor_total, war_total FROM nba.raptor ORDER BY model"
    ) == [
        ("historical", lebron, 8.1, None),
        ("modern", lebron, 7.9, 15.2),
    ]
    assert check(con, gate("seasons_raptor_resolves_under_0_1_percent")).violations == 0

    insert(con, "fte.raptor_player_modern", [{"player_id": "ghost01", "season": 2016}])
    build_models(con, *MODELS)
    assert check(con, gate("seasons_raptor_resolves_under_0_1_percent")).sample == [
        {"unresolved": 1, "total": 3}
    ]


def test_awards_normalize_votes_selections_and_teams_into_one_shape(
    con: duckdb.DuckDBPyConnection,
) -> None:
    insert(
        con,
        "bref.player_award_shares",
        [
            {
                "season": 2013,
                "award": "nba mvp",
                "player_id": "jamesle01",
                "share": 0.998,
                "winner": True,
                "first": 120.0,
            }
        ],
    )
    insert(
        con,
        "bref.all_star_selections",
        [{"season": 2013, "lg": "NBA", "player_id": "jamesle01", "team": "East", "replaced": True}],
    )
    insert(
        con,
        "bref.end_of_season_teams",
        [
            {
                "season": 2013,
                "lg": "NBA",
                "type": "All-NBA",
                "number_tm": "1st",
                "player_id": "jamesle01",
            }
        ],
    )

    build_models(con, *MODELS)

    assert rows(
        con,
        "SELECT season, lg, award, detail, share, winner, first_place_votes "
        "FROM nba.awards ORDER BY award",
    ) == [
        (2013, "NBA", "all_nba", "1st", None, True, None),
        (2013, "NBA", "all_star", "East", None, False, None),
        (2013, "NBA", "mvp", None, 0.998, True, 120.0),
    ]


def test_team_season_stats_join_opponent_stats_and_resolve_the_franchise(
    con: duckdb.DuckDBPyConnection,
) -> None:
    team = {"season": 1960, "lg": "NBA", "team": "Minneapolis Lakers"}
    insert(con, "bref.team_totals", [{**team, "abbreviation": "MNL", "pts": 7953}])
    insert(con, "bref.team_per_100", [{**team, "pts_per_100_poss": 95.0}])
    insert(con, "bref.opponent_totals", [{**team, "opp_pts": 8256}])

    build_models(con, *MODELS)

    assert rows(
        con, "SELECT season, team_id, pts, pts_per_100_poss, opp_pts FROM nba.team_season_stats"
    ) == [(1960, LAL, 7953, 95.0, 8256)]
    names = (
        "seasons_team_season_stats_key_unique",
        "seasons_player_seasons_key_unique",
        "seasons_player_seasons_players_exist",
    )
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)
