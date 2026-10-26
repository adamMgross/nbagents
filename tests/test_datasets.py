from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from nbalake import datasets
from nbalake.model import Csv, Dataset, DropFolder, GitDir, GitTree, Kaggle, ReleaseAssets
from nbalake.stage import LINEAGE

ALL = datasets.ALL
NAMES = [d.name for d in ALL]
SDV = [d for d in ALL if d.schema == "sdv"]
SDV_ASSETS: dict[str, list[str]] = json.loads(
    (Path(__file__).parent / "fixtures" / "sdv_assets.json").read_text()
)


def literal(match: str) -> str:
    return re.sub(r"\\(.)", r"\1", match)


def release_tag(ds: Dataset) -> str:
    assert isinstance(ds.fetch, ReleaseAssets), ds.name
    return ds.fetch.tag


def sample_key(ds: Dataset) -> str:
    match ds.fetch:
        case ReleaseAssets(tag=tag):
            return next(n for n in SDV_ASSETS[tag] if ds.groups(n) is not None)
        case Kaggle(slug=slug):
            return f"{slug}.zip"
        case GitDir(match=match):
            if ds.schema == "shuf":
                return f"{ds.table}_2015.tar.xz"
            return literal(match)
        case DropFolder(match=match):
            return literal(match)
        case GitTree():
            folder = {
                "player": "player_shooting",
                "team": "team_shooting",
                "opponent": "opp_shooting",
            }
            return f"2016/{folder[ds.table.split('_')[0]]}/wide_open.csv"


def test_names_are_unique_schema_dot_table() -> None:
    assert len(set(NAMES)) == len(NAMES)
    assert all(re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", n) for n in NAMES), NAMES
    assert all(d.name == f"{d.schema}.{d.table}" for d in ALL)
    assert {d.name: d for d in ALL} == datasets.BY_NAME
    assert tuple(sorted({d.schema for d in ALL})) == datasets.SCHEMAS


def test_every_fetch_match_compiles_as_a_full_key_pattern() -> None:
    for d in ALL:
        pattern = re.compile(d.fetch.match)
        assert pattern.fullmatch(sample_key(d)), (d.name, sample_key(d))


def test_partition_is_never_a_lineage_column() -> None:
    offenders = [d.name for d in ALL if d.partition in LINEAGE]
    assert not offenders, offenders


def test_sort_tuples_have_no_duplicates() -> None:
    offenders = [d.name for d in ALL if len(set(d.sort)) != len(d.sort)]
    assert not offenders, offenders


def test_no_two_datasets_load_the_same_source_the_same_way() -> None:
    seen: dict[tuple[object, object], str] = {}
    clashes = []
    for d in ALL:
        first = seen.setdefault((d.fetch, d.parse), d.name)
        if first != d.name:
            clashes.append((first, d.name))
    assert not clashes, clashes


def test_csv_datasets_sharing_an_archive_each_name_their_member() -> None:
    by_fetch: dict[object, list[Csv]] = {}
    for d in ALL:
        if isinstance(d.parse, Csv):
            by_fetch.setdefault(d.fetch, []).append(d.parse)
    unnamed = [
        fetch
        for fetch, parses in by_fetch.items()
        if len(parses) > 1 and any(p.member is None for p in parses)
    ]
    assert not unnamed, unnamed


def test_select_exact_name_returns_that_dataset_only() -> None:
    assert datasets.select(["sdv.nba_stats_pbp"]) == [datasets.BY_NAME["sdv.nba_stats_pbp"]]


def test_select_schema_returns_every_dataset_in_registry_order() -> None:
    assert datasets.select(["fte"]) == [d for d in ALL if d.schema == "fte"]
    assert datasets.select(("bref",)) == [d for d in ALL if d.schema == "bref"]


def test_select_glob_matches_full_names() -> None:
    assert [d.name for d in datasets.select(["fte.raptor_*_modern"])] == [
        "fte.raptor_player_modern",
        "fte.raptor_team_modern",
    ]
    assert [d.name for d in datasets.select(["*_officials"])] == [
        "sdv.nba_stats_officials",
        "sdv.espn_nba_officials",
    ]


def test_select_unions_patterns_in_registry_order_without_duplicates() -> None:
    chosen = datasets.select(["bref.team_totals", "sdv.nba_stats_pbp", "l2m", "l2m.calls"])

    assert [d.name for d in chosen] == [
        "sdv.nba_stats_pbp",
        "l2m.calls",
        "l2m.teams",
        "bref.team_totals",
    ]
    assert datasets.select(["sdv", "sdv.nba_stats_pbp"]) == datasets.select(["sdv"])


@pytest.mark.parametrize("patterns", [["nope"], ["l2m", "nope"], ["l2"], ["sdv.nba_stats"]])
def test_select_raises_key_error_naming_the_pattern_nothing_matches(
    patterns: list[str],
) -> None:
    with pytest.raises(KeyError, match=re.escape(patterns[-1])):
        datasets.select(patterns)


def test_select_with_no_patterns_returns_the_whole_registry() -> None:
    assert datasets.select([]) == list(ALL)
    assert datasets.select(()) == list(ALL)


def test_every_sdv_asset_is_claimed_by_exactly_one_dataset() -> None:
    orphans = []
    for tag, names in SDV_ASSETS.items():
        for name in names:
            if not name.endswith(".parquet"):
                continue
            hits = [d.name for d in SDV if release_tag(d) == tag and d.groups(name) is not None]
            if len(hits) != 1:
                orphans.append((tag, name, hits))
    assert not orphans, f"assets not matched by exactly one sdv dataset: {orphans}"


def test_every_sdv_dataset_claims_at_least_one_asset() -> None:
    idle = [
        d.name
        for d in SDV
        if not any(d.groups(n) is not None for n in SDV_ASSETS.get(release_tag(d), []))
    ]
    assert not idle, f"sdv datasets matching no upstream asset: {idle}"


@pytest.mark.parametrize("ds", ALL, ids=NAMES)
def test_columns_for_a_sample_key_yields_only_int_or_str_values(ds: Dataset) -> None:
    cols = ds.columns_for(sample_key(ds))

    assert all(isinstance(v, int | str) for v in cols.values()), cols
    assert all(c not in LINEAGE for c in cols), cols


@pytest.mark.parametrize("ds", SDV, ids=[d.name for d in SDV])
def test_sdv_unit_columns_are_the_named_groups_with_season_as_an_int(ds: Dataset) -> None:
    key = sample_key(ds)
    groups = ds.groups(key)
    assert groups is not None
    cols = ds.columns_for(key)

    assert set(cols) == set(groups)
    if "season" in groups:
        assert cols["season"] == int(groups["season"])
        assert ds.partition == "season" or ds.sort[:1] == ("season",)
    for name, value in groups.items():
        if name != "season":
            assert cols[name] == value


@pytest.mark.parametrize("ds", [d for d in ALL if d.schema == "shuf"], ids=lambda d: d.name)
def test_shufinskiy_season_is_start_year_plus_one_and_po_marks_playoffs(ds: Dataset) -> None:
    assert ds.columns_for(f"{ds.table}_2015.tar.xz") == {
        "season": 2016,
        "season_type": "regular",
    }
    assert ds.columns_for(f"{ds.table}_po_1996.tar.xz") == {
        "season": 1997,
        "season_type": "playoffs",
    }
    assert ds.groups(f"{ds.table}_po2015.tar.xz") is None


def test_columns_for_a_key_that_does_not_match_raises_value_error() -> None:
    ds = datasets.BY_NAME["sdv.nba_stats_pbp"]

    with pytest.raises(ValueError, match=re.escape("does not match sdv.nba_stats_pbp")):
        ds.columns_for("nba_play_by_play_2020.csv")


@pytest.mark.parametrize("name", ["bad", "a.b.c", ".table", "schema.", "."])
def test_dataset_name_without_exactly_one_dot_raises_value_error(name: str) -> None:
    with pytest.raises(ValueError, match=re.escape("<schema>.<table>")):
        Dataset(name, ReleaseAssets("tag", r".*\.parquet"))


def test_dataset_with_an_invalid_match_pattern_raises_at_construction() -> None:
    with pytest.raises(re.error):
        Dataset("t.x", ReleaseAssets("tag", r"(unclosed"))


def test_dataset_schema_table_and_qualified_name_derive_from_name() -> None:
    ds = Dataset("fte.elo", GitDir("o/r", "p", r"x\.csv"))

    assert (ds.schema, ds.table) == ("fte", "elo")
    assert ds.qualified == 'lake."fte"."elo"'


def test_only_the_large_season_replaced_tables_are_partitioned() -> None:
    assert {d.name for d in datasets.ALL if d.partition} == {
        "sdv.nba_stats_pbp",
        "sdv.espn_nba_pbp",
        "shuf.nbastats",
        "shuf.nbastatsv3",
        "shuf.pbpstats",
    }
    assert all(d.partition == "season" for d in datasets.ALL if d.partition)


def test_the_guide_lists_exactly_the_staged_tables_no_model_reads() -> None:
    import duckdb

    from nbalake.curate import shipped_steps
    from nbalake.fingerprint import references

    con = duckdb.connect()
    read = {r for s in shipped_steps() for r in references(con, s.sql)}
    unread = {d.name for d in datasets.ALL} - read
    guide = (Path(__file__).parent.parent / "docs" / "dataset-guide.md").read_text()
    section = guide.split("## Staged-only data", 1)[1].split("\n## ", 1)[0]
    listed = re.findall(r"`([a-z0-9_]+\.[a-z0-9_*]+)`", section)
    patterns = [re.compile(re.escape(n).replace(r"\*", "[a-z0-9_]*") + "$") for n in listed]

    assert sorted(n for n in unread if not any(p.match(n) for p in patterns)) == []
    staged = [n for n in listed if n.split(".", 1)[0] != "nba"]
    assert sorted(n for n in staged if "*" not in n and n not in unread) == []


@pytest.mark.parametrize(
    ("ds", "folder"),
    [
        (datasets.BY_NAME["gab.player_shots_by_defender"], "player_shooting"),
        (datasets.BY_NAME["gab.team_shots_by_defender"], "team_shooting"),
        (datasets.BY_NAME["gab.opponent_shots_by_defender"], "opp_shooting"),
    ],
    ids=lambda x: x if isinstance(x, str) else x.name,
)
def test_closest_defender_paths_give_end_year_season_type_and_band(
    ds: Dataset, folder: str
) -> None:
    assert ds.columns_for(f"2016/{folder}/wide_open.csv") == {
        "season": 2016,
        "season_type": "regular",
        "defender_distance": "wide_open",
    }
    assert ds.columns_for(f"2014/playoffs/{folder}/very_tight.csv") == {
        "season": 2014,
        "season_type": "playoffs",
        "defender_distance": "very_tight",
    }
    assert ds.groups(f"2026/{folder}/{folder}.csv") is None
    assert ds.groups(f"2026/{folder}/open.csv.bak") is None
