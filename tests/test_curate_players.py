from __future__ import annotations

from collections.abc import Iterator

import duckdb
import pytest

from nbalake.curate import check
from nbalake.lake import Root
from tests.curated import build_models, empty_lake, gate, insert, rows, sources

TABLES = (
    "sdv.nba_stats_player_boxscores",
    "sdv.leaguedash_player_bio",
    "sdv.nba_player_crosswalk",
    "sdv.espn_nba_player_core",
    "sdv.espn_nba_player_boxscores",
    "sdv.espn_nba_injuries",
    "sdv.espn_nba_depthcharts",
    "bref.player_career_info",
    "bref.player_totals",
    "fte.raptor_player_historical",
    "fte.raptor_player_modern",
    "sdv.draft_combine_stats",
    "sdv.draft_combine_playeranthro",
    "sdv.draft_combine_drillresults",
    "sdv.draft_combine_spotshooting",
    "sdv.draft_combine_nonstationaryshooting",
)
MODELS = ("franchises", "espn_bref_links", "player_xref", "players", "unresolved_players")
LAL, CLE, ATL = "LAL", "CLE", "ATL"
LAL_ID, CLE_ID, ATL_ID = 1610612747, 1610612739, 1610612737
MINTED = 9000000000000


def nba(
    person_id: int, first: str, family: str, seasons: range, team_id: int = LAL_ID
) -> list[dict]:
    return [
        {
            "person_id": person_id,
            "first_name": first,
            "family_name": family,
            "season": s,
            "team_id": team_id,
        }
        for s in seasons
    ]


def bref(
    slug: str, name: str, seasons: range, team: str = LAL, **info: object
) -> tuple[dict, list[dict]]:
    career = {
        "player_id": slug,
        "player": name,
        "from": seasons.start,
        "to": seasons.stop - 1,
        **info,
    }
    return career, [{"player_id": slug, "season": s, "team": team} for s in seasons]


def add(con: duckdb.DuckDBPyConnection, *players: tuple[dict, list[dict]] | list[dict]) -> None:
    for p in players:
        if isinstance(p, tuple):
            insert(con, "bref.player_career_info", [p[0]])
            insert(con, "bref.player_totals", p[1])
        else:
            insert(con, "sdv.nba_stats_player_boxscores", p)


def canonical(con: duckdb.DuckDBPyConnection, source: str, source_id: str) -> tuple:
    found = rows(
        con,
        "SELECT player_id, method FROM nba.player_xref WHERE source = ? AND source_id = ?",
        [source, source_id],
    )
    return found[0] if found else (None, None)


@pytest.fixture
def con(root: Root) -> Iterator[duckdb.DuckDBPyConnection]:
    con = empty_lake(root, TABLES)
    yield con
    con.close()


def test_names_match_across_accents_suffixes_and_punctuation(
    con: duckdb.DuckDBPyConnection,
) -> None:
    add(
        con,
        nba(1629029, "Luka", "Doncic", range(2019, 2022)),
        bref("doncilu01", "Luka Dončić", range(2019, 2022)),
        nba(1629018, "Gary", "Trent Jr.", range(2019, 2021)),
        bref("trentga02", "Gary Trent", range(2019, 2021)),
    )

    build_models(con, *MODELS)

    assert canonical(con, "bref", "doncilu01") == (1629029, "name")
    assert canonical(con, "bref", "trentga02") == (1629018, "name")


def test_reversed_name_order_matches_on_the_token_set(con: duckdb.DuckDBPyConnection) -> None:
    add(
        con,
        nba(2397, "Ming", "Yao", range(2003, 2012)),
        bref("mingya01", "Yao Ming", range(2003, 2012)),
    )

    build_models(con, *MODELS)

    assert canonical(con, "bref", "mingya01") == (2397, "name_tokens")


def test_namesakes_with_overlapping_careers_split_on_their_team_seasons(
    con: duckdb.DuckDBPyConnection,
) -> None:
    add(
        con,
        nba(203187, "Chris", "Johnson", range(2013, 2017), CLE_ID),
        nba(202419, "Chris", "Johnson", range(2011, 2014), ATL_ID),
        bref("johnsch04", "Chris Johnson", range(2013, 2017), CLE),
        bref("johnsch03", "Chris Johnson", range(2011, 2014), ATL),
    )

    build_models(con, *MODELS)

    assert canonical(con, "bref", "johnsch04") == (203187, "team_season_name")
    assert canonical(con, "bref", "johnsch03") == (202419, "team_season_name")


def test_a_nickname_links_through_several_shared_team_seasons_and_the_family_name(
    con: duckdb.DuckDBPyConnection,
) -> None:
    add(
        con,
        nba(1630286, "Trevon", "Scott", range(2022, 2027)),
        bref("scotttr01", "Tre Scott", range(2022, 2027)),
    )

    build_models(con, *MODELS)

    assert canonical(con, "bref", "scotttr01") == (1630286, "team_season_name")


def test_an_exact_name_wins_over_a_teammate_who_shares_only_the_surname(
    con: duckdb.DuckDBPyConnection,
) -> None:
    add(
        con,
        nba(1, "Charles", "Smith", range(1998, 2000)),
        nba(2, "Charles", "Smith", range(1999, 2001), CLE_ID),
        nba(3, "Steven", "Smith", range(1998, 2000)),
        bref("smithch04", "Charles Smith", range(1998, 2000)),
        bref("smithch05", "Charles Smith", range(1999, 2001), CLE),
        bref("smithst01", "Steve Smith", range(1998, 2000)),
    )

    build_models(con, *MODELS)

    assert canonical(con, "bref", "smithch04") == (1, "team_season_name")
    assert canonical(con, "bref", "smithch05") == (2, "team_season_name")
    assert canonical(con, "bref", "smithst01") == (3, "team_season_name")


def test_pre_1997_players_get_a_stable_minted_id_outside_the_nba_range(
    con: duckdb.DuckDBPyConnection,
) -> None:
    add(con, bref("chambwi01", "Wilt Chamberlain", range(1960, 1974)))

    build_models(con, *MODELS)
    first = canonical(con, "bref", "chambwi01")
    build_models(con, *MODELS)

    assert first == canonical(con, "bref", "chambwi01")
    assert first[1] == "minted" and MINTED <= first[0] < 2 * MINTED
    assert rows(con, "SELECT nba_player_id, bref_id FROM nba.players") == [(None, "chambwi01")]


def test_espn_ids_resolve_by_crosswalk_then_birth_date_then_span(
    con: duckdb.DuckDBPyConnection,
) -> None:
    add(
        con,
        nba(2544, "LeBron", "James", range(2004, 2006)),
        bref("jamesle01", "LeBron James", range(2004, 2006), birth_date="1984-12-30"),
        bref("ewingpa01", "Patrick Ewing", range(1986, 2003), birth_date="1962-08-05"),
        bref("ewingpa02", "Patrick Ewing", range(2011, 2012), birth_date="1984-05-20"),
        bref("smitsri01", "Rik Smits", range(1989, 2001)),
    )
    insert(
        con,
        "sdv.nba_player_crosswalk",
        [{"season": 2005, "espn_athlete_id": "1966", "nba_player_id": "2544"}],
    )
    insert(
        con,
        "sdv.espn_nba_player_core",
        [
            {
                "season": 1995,
                "athlete_id": 100,
                "full_name": "Patrick Ewing",
                "date_of_birth": "1962-08-05T07:00Z",
            },
            {
                "season": 2011,
                "athlete_id": 101,
                "full_name": "Patrick Ewing",
                "date_of_birth": "1984-05-20T07:00Z",
            },
        ],
    )
    insert(
        con,
        "sdv.espn_nba_player_boxscores",
        [
            {"season": 1995, "athlete_id": 102, "athlete_display_name": "Rik Smits"},
            {"season": 1995, "athlete_id": 103, "athlete_display_name": "Never Played"},
        ],
    )

    build_models(con, *MODELS)

    assert canonical(con, "espn", "1966") == (2544, "crosswalk")
    assert canonical(con, "espn", "100") == (
        canonical(con, "bref", "ewingpa01")[0],
        "name_birth_date",
    )
    assert canonical(con, "espn", "101") == (
        canonical(con, "bref", "ewingpa02")[0],
        "name_birth_date",
    )
    assert canonical(con, "espn", "102") == (canonical(con, "bref", "smitsri01")[0], "name_span")
    assert rows(con, "SELECT source, source_id FROM nba.unresolved_players") == [("espn", "103")]


def test_fte_slugs_resolve_through_basketball_reference(con: duckdb.DuckDBPyConnection) -> None:
    add(con, bref("jamesle01", "LeBron James", range(2004, 2006)))
    insert(
        con,
        "fte.raptor_player_modern",
        [
            {"player_id": "jamesle01", "player_name": "LeBron James", "season": 2014},
            {"player_id": "nobody01", "player_name": "Nobody", "season": 2014},
        ],
    )

    build_models(con, *MODELS)

    assert canonical(con, "fte", "jamesle01") == (
        canonical(con, "bref", "jamesle01")[0],
        "bref_slug",
    )
    assert rows(con, "SELECT source, source_id FROM nba.unresolved_players") == [
        ("fte", "nobody01")
    ]


def test_players_prefer_nba_bio_then_bref_and_null_the_sentinels(
    con: duckdb.DuckDBPyConnection,
) -> None:
    add(
        con,
        nba(2617, "Udonis", "Haslem", range(2004, 2006)),
        bref(
            "hasleud01",
            "Udonis Haslem",
            range(2004, 2006),
            ht_in_in=79,
            wt=230,
            colleges="Florida",
            hof=False,
        ),
    )
    insert(
        con,
        "sdv.leaguedash_player_bio",
        [
            {
                "player_id": 2617,
                "player_name": "Udonis Haslem",
                "season": 2005,
                "player_height_inches": 80,
                "player_weight": "235",
                "college": "None",
                "country": "USA",
                "draft_year": "Undrafted",
                "draft_round": "Undrafted",
                "draft_number": "Undrafted",
            }
        ],
    )

    build_models(con, *MODELS)

    assert rows(
        con,
        "SELECT player_id, first_name, last_name, height_inches, weight_lbs, college, draft_year, "
        "from_season, to_season, bref_id FROM nba.players",
    ) == [(2617, "Udonis", "Haslem", 80, 235, "Florida", None, 2004, 2005, "hasleud01")]


def test_players_gates_pass_on_resolved_ids_and_flag_each_violation(
    con: duckdb.DuckDBPyConnection,
) -> None:
    add(
        con,
        nba(2544, "LeBron", "James", range(2004, 2006)),
        bref("jamesle01", "LeBron James", range(2004, 2006)),
        bref("chambwi01", "Wilt Chamberlain", range(1960, 1974)),
    )
    build_models(con, *MODELS)
    names = (
        "players_player_id_unique",
        "players_xref_key_unique",
        "players_one_nba_and_one_bref_id_per_player",
        "players_bref_careers_since_1997_have_an_nba_id",
        "players_box_person_ids_resolve",
        "players_bref_ids_resolve",
    )
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)

    add(con, bref("unknown01", "Played Lately", range(2010, 2012)))
    build_models(con, *MODELS)
    add(con, nba(99, "Late", "Box", range(2012, 2013)))
    insert(con, "bref.player_totals", [{"player_id": "ghost01", "season": 2012, "team": LAL}])
    insert(con, "nba.player_xref", [{"source": "bref", "source_id": "dupe01", "player_id": 2544}])

    minted = check(con, gate("players_bref_careers_since_1997_have_an_nba_id"))
    assert [r["source_id"] for r in minted.sample] == ["unknown01"]
    assert check(con, gate("players_box_person_ids_resolve")).sample == [{"person_id": 99}]
    assert check(con, gate("players_bref_ids_resolve")).sample == [{"player_id": "ghost01"}]
    doubled = check(con, gate("players_one_nba_and_one_bref_id_per_player"))
    assert [(r["player_id"], r["source"]) for r in doubled.sample] == [(2544, "bref")]


def combine(player_id: int, first: str, last: str, season: int = 2004, **values: object) -> dict:
    return {
        "season": season,
        "player_id": player_id,
        "first_name": first,
        "last_name": last,
        "player_name": f"{first} {last}",
        "position": "SF",
        **values,
    }


def test_the_draft_combine_keeps_prospects_on_their_nba_stats_id_and_says_who_played(
    con: duckdb.DuckDBPyConnection,
) -> None:
    add(con, nba(2544, "LeBron", "James", range(2004, 2006)))
    insert(
        con,
        "sdv.draft_combine_stats",
        [combine(2544, "LeBron", "James", wingspan=84.25), combine(77, "Never", "Played")],
    )
    insert(
        con,
        "sdv.draft_combine_spotshooting",
        [combine(2544, "LeBron", "James", fifteen_corner_left_made=3)],
    )
    build_models(con, *MODELS, "draft_combine")
    names = (
        "players_draft_combine_key_unique",
        "players_draft_combine_ids_match_player_names_over_98_percent",
    )

    measured = "SELECT player_id, played, wingspan, fifteen_corner_left_made FROM nba.draft_combine"
    assert rows(con, measured + " ORDER BY 1") == [(77, False, None, None), (2544, True, 84.25, 3)]
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)

    insert(con, "sdv.draft_combine_stats", [combine(2544, "Wrong", "Person", season=2005)])
    build_models(con, *MODELS, "draft_combine")

    assert check(con, gate(names[1])).sample == [{"mismatched": 1, "ids": 2}]


def test_the_espn_link_seed_resolves_a_name_no_rule_matches_and_null_ids_are_not_players(
    con: duckdb.DuckDBPyConnection,
) -> None:
    add(con, bref("boguemu01", "Muggsy Bogues", range(1988, 2002)))
    insert(
        con,
        "sdv.espn_nba_player_boxscores",
        [
            {"athlete_id": 73, "athlete_display_name": "Tyrone Bogues", "season": 1995},
            {"athlete_id": None, "athlete_display_name": None, "season": 2026},
        ],
    )
    build_models(con, *MODELS)

    assert canonical(con, "espn", "73") == (canonical(con, "bref", "boguemu01")[0], "seed")
    assert rows(con, "SELECT source_id FROM nba.unresolved_players WHERE source = 'espn'") == []


def test_an_espn_athlete_without_a_bref_slug_resolves_to_the_one_nba_stats_namesake_in_span(
    con: duckdb.DuckDBPyConnection,
) -> None:
    add(
        con,
        nba(1642284, "Alex", "Karaban", range(2027, 2028)),
        nba(1, "John", "Smith", range(2027, 2028)),
        nba(2, "John", "Smith", range(2026, 2028)),
        nba(3, "Old", "Timer", range(2001, 2003)),
        nba(4, "Taken", "Name", range(2027, 2028)),
    )
    insert(
        con,
        "sdv.nba_player_crosswalk",
        [{"season": 2027, "espn_athlete_id": "500", "nba_player_id": "4"}],
    )
    insert(
        con,
        "sdv.espn_nba_depthcharts",
        [
            {"season": 2027, "athlete_id": 4917149, "athlete_display_name": "Alex Karaban"},
            {"season": 2027, "athlete_id": 600, "athlete_display_name": "John Smith"},
            {"season": 2027, "athlete_id": 601, "athlete_display_name": "Taken Name"},
        ],
    )
    insert(
        con,
        "sdv.espn_nba_injuries",
        [{"season": 2027, "athlete_id": 700, "athlete_display_name": "Old Timer"}],
    )

    build_models(con, *MODELS)

    assert canonical(con, "espn", "4917149") == (1642284, "nba_name_span")
    assert canonical(con, "espn", "500") == (4, "crosswalk")
    assert [canonical(con, "espn", i) for i in ("600", "601", "700")] == [(None, None)] * 3


SNAPSHOT_MODELS = (
    "franchises",
    "team_seasons",
    "espn_bref_links",
    "player_xref",
    "injuries",
    "injuries_latest",
    "depth_charts",
    "depth_charts_latest",
)


def injury(fetched: str, day: str, athlete: int, name: str, **extra: object) -> dict:
    return {
        "_fetched_at": fetched,
        "as_of_date": day,
        "season": 2027,
        "team_id": 13,
        "athlete_id": athlete,
        "athlete_display_name": name,
        "status": "Out",
        "injury_date": "2026-10-23T17:22Z",
        "detail_return_date": "2026-10-25",
        **extra,
    }


@pytest.fixture
def snapshots(root: Root) -> Iterator[duckdb.DuckDBPyConnection]:
    con = empty_lake(root, sources(*SNAPSHOT_MODELS, gate_prefix="players_injur"))
    insert(
        con,
        "sdv.nba_team_crosswalk",
        [{"season": 2027, "espn_team_id": 13, "nba_team_id": str(LAL_ID)}],
    )
    insert(con, "sdv.nba_stats_player_boxscores", nba(2544, "LeBron", "James", range(2027, 2028)))
    insert(
        con,
        "sdv.nba_player_crosswalk",
        [{"season": 2027, "espn_athlete_id": "1966", "nba_player_id": "2544"}],
    )
    yield con
    con.close()


def test_injuries_keep_each_dates_snapshot_from_the_newest_capture_with_resolved_ids(
    snapshots: duckdb.DuckDBPyConnection,
) -> None:
    older, newer = "2026-10-22T05:10:13+00:00", "2026-10-23T07:27:41+00:00"
    insert(
        snapshots,
        "sdv.espn_nba_injuries",
        [
            injury(older, "2026-10-21", 1966, "LeBron James", status="Day-To-Day"),
            injury(newer, "2026-10-21", 1966, "LeBron James"),
            injury(newer, "2026-10-22", 1966, "LeBron James"),
            injury(newer, "2026-10-22", 5142718, "AJ Dybantsa"),
        ],
    )

    build_models(snapshots, *SNAPSHOT_MODELS)

    assert rows(
        snapshots,
        "SELECT snapshot_date::VARCHAR, player_id, espn_athlete_id, team_id, status, "
        "reported_at::VARCHAR, return_date::VARCHAR, fetched_at FROM nba.injuries ORDER BY 1, 3",
    ) == [
        ("2026-10-21", 2544, 1966, LAL_ID, "Out", "2026-10-23 17:22:00", "2026-10-25", newer),
        ("2026-10-22", 2544, 1966, LAL_ID, "Out", "2026-10-23 17:22:00", "2026-10-25", newer),
        ("2026-10-22", None, 5142718, LAL_ID, "Out", "2026-10-23 17:22:00", "2026-10-25", newer),
    ]
    assert rows(
        snapshots, "SELECT snapshot_date::VARCHAR, player_name FROM nba.injuries_latest ORDER BY 2"
    ) == [("2026-10-22", "AJ Dybantsa"), ("2026-10-22", "LeBron James")]


def test_depth_charts_rank_each_position_per_snapshot_and_the_latest_view_is_the_newest(
    snapshots: duckdb.DuckDBPyConnection,
) -> None:
    fetched = "2026-10-23T07:27:41+00:00"
    slot = {"_fetched_at": fetched, "season": 2027, "team_id": 13, "position_abbreviation": "sf"}
    insert(
        snapshots,
        "sdv.espn_nba_depthcharts",
        [
            {**slot, "as_of_date": "2026-10-21", "depth_rank": 1, "athlete_id": 1966},
            {**slot, "as_of_date": "2026-10-22", "depth_rank": 1, "athlete_id": 1966},
            {**slot, "as_of_date": "2026-10-22", "depth_rank": 2, "athlete_id": 99},
        ],
    )

    build_models(snapshots, *SNAPSHOT_MODELS)

    assert rows(
        snapshots,
        "SELECT position, depth_rank, player_id, team_id FROM nba.depth_charts_latest ORDER BY 2",
    ) == [("sf", 1, 2544, LAL_ID), ("sf", 2, None, LAL_ID)]


def test_injury_and_depth_chart_gates_pass_on_snapshots_and_flag_each_violation(
    snapshots: duckdb.DuckDBPyConnection,
) -> None:
    fetched = "2026-10-23T07:27:41+00:00"
    insert(snapshots, "sdv.espn_nba_injuries", [injury(fetched, "2026-10-22", 1966, "LeBron")])
    build_models(snapshots, *SNAPSHOT_MODELS)
    names = (
        "players_injuries_key_unique",
        "players_depth_charts_key_unique",
        "players_injury_and_depth_chart_teams_resolve",
        "players_injury_and_depth_chart_players_resolve_over_85_percent",
    )
    assert {n: check(snapshots, gate(n)).violations for n in names} == dict.fromkeys(names, 0)

    insert(
        snapshots,
        "sdv.espn_nba_injuries",
        [
            injury(fetched, "2026-10-22", 1966, "LeBron"),
            injury(fetched, "2026-10-22", 7, "X"),
            injury(fetched, "2026-10-22", 8, "Y", team_id=99),
        ],
    )
    build_models(snapshots, *SNAPSHOT_MODELS)

    assert check(snapshots, gate("players_injuries_key_unique")).violations == 1
    assert check(snapshots, gate("players_injury_and_depth_chart_teams_resolve")).violations == 1
    assert check(
        snapshots, gate("players_injury_and_depth_chart_players_resolve_over_85_percent")
    ).sample == [{"resolved": 2, "listed": 4}]


def test_a_nameless_box_row_is_a_coach_not_a_player(con: duckdb.DuckDBPyConnection) -> None:
    add(
        con,
        nba(2544, "LeBron", "James", range(2004, 2006)),
        nba(1345, "", "", range(1998, 2000)),
    )

    build_models(con, *MODELS)

    assert rows(con, "SELECT player_id FROM nba.players") == [(2544,)]
    assert canonical(con, "nba", "1345") == (None, None)
    names = ("players_box_person_ids_resolve", "players_every_player_has_a_name")
    assert {n: check(con, gate(n)).violations for n in names} == dict.fromkeys(names, 0)

    con.execute("UPDATE nba.players SET name = ' ' WHERE player_id = 2544")
    assert check(con, gate("players_every_player_has_a_name")).sample == [{"player_id": 2544}]
