from __future__ import annotations

from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Any

import duckdb
import pytest

from nbalake.explore import macros

SEASONS = (1999, 2000, 2001)
STAR, ROLE = 1, 2


@dataclass
class League:
    teams: dict[int, int] = field(default_factory=lambda: dict.fromkeys(SEASONS, 2))
    population: dict[int, int] = field(
        default_factory=lambda: {1999: 1_000_000_000, 2000: 1_100_000_000, 2001: 1_300_000_000}
    )
    bpm: dict[tuple[int, int], float] = field(default_factory=dict)
    two_trips: dict[int, int] = field(default_factory=lambda: dict.fromkeys(SEASONS, 2))
    bonus_trips: dict[int, int] = field(default_factory=lambda: dict.fromkeys(SEASONS, 0))


def lake(league: League) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("CREATE SCHEMA nba")
    con.execute(
        "CREATE TABLE nba.team_seasons (season INTEGER, lg VARCHAR, team_id BIGINT, w INTEGER, "
        "l INTEGER, n_rtg DOUBLE, pace DOUBLE)"
    )
    con.execute(
        "CREATE TABLE nba.team_season_stats (season INTEGER, lg VARCHAR, team_id BIGINT, "
        "mp DOUBLE, g INTEGER, fta DOUBLE, x3pa DOUBLE)"
    )
    con.execute(
        "CREATE TABLE nba.player_seasons (season INTEGER, lg VARCHAR, player_id HUGEINT, "
        "bref_id VARCHAR, player VARCHAR, age INTEGER, mp DOUBLE, bpm DOUBLE, ft DOUBLE, "
        "fta DOUBLE, multi_team BOOLEAN)"
    )
    con.execute(
        "CREATE TABLE nba.pbp (game_id VARCHAR, order_index BIGINT, season INTEGER, "
        "player_id BIGINT, sub_type VARCHAR, is_foul BOOLEAN, is_free_throw BOOLEAN)"
    )
    con.execute(
        "CREATE TABLE nba.shots (game_id VARCHAR, season INTEGER, shot_value INTEGER, "
        "shot_distance INTEGER, made BOOLEAN)"
    )
    con.execute("CREATE TABLE nba.us_population (year INTEGER, population BIGINT)")
    con.execute("CREATE TABLE nba.player_birthplaces (bref_id VARCHAR, born_in_us BOOLEAN)")
    con.execute("CREATE TABLE nba.players (player_id HUGEINT, from_season INTEGER)")
    con.execute("INSERT INTO nba.player_birthplaces VALUES ('star01', true), ('role01', false)")
    con.execute(f"INSERT INTO nba.players VALUES ({STAR}, 1999), ({ROLE}, 1995)")
    for season in SEASONS:
        con.execute(
            "INSERT INTO nba.us_population VALUES (?, ?)", [season, league.population[season]]
        )
        for team in range(1, league.teams[season] + 1):
            good = team % 2 == 1
            con.execute(
                "INSERT INTO nba.team_seasons VALUES (?, 'NBA', ?, ?, ?, ?, 100)",
                [season, team, 50 if good else 32, 32 if good else 50, 5.0 if good else -5.0],
            )
            con.execute(
                "INSERT INTO nba.team_season_stats VALUES (?, 'NBA', ?, 19680, 82, 2000, 1000)",
                [season, team],
            )
        for player, slug, ft, fta in ((STAR, "star01", 400, 500), (ROLE, "role01", 0, 0)):
            bpm = league.bpm.get((season, player), 5.0 if player == STAR else 0.0)
            con.execute(
                "INSERT INTO nba.player_seasons "
                "VALUES (?, 'NBA', ?, ?, ?, 27, 3000, ?, ?, ?, false)",
                [season, player, slug, slug, bpm, ft, fta],
            )
        game = f"002{season}0001"
        events = (
            [("Shooting", "Free Throw 1 of 2")] * league.two_trips[season]
            + [("Personal", "Free Throw 1 of 2")] * league.bonus_trips[season]
            + [("Shooting", "Free Throw 1 of 1"), ("Shooting", "Free Throw 1 of 3")]
        )
        order = 0
        for foul, free_throw in events:
            for sub_type, is_foul, player in ((foul, True, 99), (free_throw, False, STAR)):
                order += 1
                con.execute(
                    "INSERT INTO nba.pbp VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [game, order, season, player, sub_type, is_foul, not is_foul],
                )
        for made in [True] * 5 + [False] * 5:
            con.execute("INSERT INTO nba.shots VALUES (?, ?, 2, 4, ?)", [game, season, made])
    for m in macros.shipped():
        con.execute(m.sql)
    return con


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, Any]]:
    cursor = con.execute(sql)
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]


def by_key(con: duckdb.DuckDBPyConnection, sql: str, *key: str) -> dict[Any, dict[str, Any]]:
    return {tuple(r[k] for k in key) if len(key) > 1 else r[key[0]]: r for r in rows(con, sql)}


def test_wins_per_point_is_the_slope_of_win_percentage_on_net_rating_times_82() -> None:
    con = lake(League())

    found = by_key(con, "FROM wins_per_point()", "season")

    assert {s: r["wins_per_point"] for s, r in found.items()} == pytest.approx(
        dict.fromkeys(SEASONS, 82 * (50 - 32) / 82 / 10)
    )


def test_whistle_trips_count_shooting_fouls_and_ones_and_three_shot_trips_but_not_bonus_trips() -> (
    None
):
    con = lake(League(two_trips=dict.fromkeys(SEASONS, 3), bonus_trips=dict.fromkeys(SEASONS, 4)))

    found = rows(con, "FROM whistle_trips() WHERE season = 2000")

    assert found == [
        {"season": 2000, "player_id": STAR, "two_trips": 3, "and_ones": 1, "three_trips": 1}
    ]


def test_free_throw_environment_rates_each_channel_and_carries_the_first_measured_season_back() -> (
    None
):
    con = lake(League(two_trips={1999: 4, 2000: 2, 2001: 2}))
    con.execute("DELETE FROM nba.pbp WHERE season = 1999")
    con.execute("INSERT INTO nba.team_season_stats VALUES (1998, 'NBA', 1, 19680, 82, 2000, 0)")

    found = by_key(con, "FROM free_throw_environment()", "season")

    assert found[2000]["two_rate"] == pytest.approx(2 / 10)
    assert found[2000]["and_one_rate"] == pytest.approx(1 / 5)
    assert found[2000]["three_rate"] == pytest.approx(1 / 2000)
    assert found[2000]["two_share"] == pytest.approx(2 * 2 / 4000)
    assert not found[1999]["measured"]
    assert found[1999]["two_rate"] == pytest.approx(found[2000]["two_rate"])
    assert found[1998]["three_share"] == 0


def test_league_strength_sums_drift_minus_each_step_to_zero_at_the_reference() -> None:
    con = lake(League(bpm={(2001, STAR): 3.0, (2001, ROLE): -1.0}))

    found = by_key(con, "FROM league_strength(reference_season := 2001)", "season")
    fit = rows(
        con,
        "SELECT regr_intercept(shock, talent_step) AS drift FROM ("
        "SELECT shock, talent_z - lag(talent_z) OVER (ORDER BY season) AS talent_step "
        "FROM league_strength())",
    )[0]

    assert found[2001]["strength"] == pytest.approx(0)
    assert found[2001]["shock"] == pytest.approx(-1.5)
    for season in (2000, 2001):
        step = found[season]["strength"] - found[season - 1]["strength"]
        assert step == pytest.approx(fit["drift"] - found[season]["shock"])


def test_talent_z_is_the_normal_quantile_of_the_us_born_share_of_the_population_in_spots() -> None:
    con = lake(League(teams={1999: 2, 2000: 2, 2001: 4}))

    found = by_key(con, "FROM league_strength()", "season")

    for season, r in found.items():
        q = r["us_spots"] / League().population[season]
        assert r["talent_z"] == pytest.approx(NormalDist().inv_cdf(1 - q), abs=5e-4)
    assert found[2001]["us_spots"] == pytest.approx(10 * 4 * 0.5)


def test_expansion_lowers_the_talent_bar_and_population_growth_raises_it() -> None:
    con = lake(League(teams={1999: 2, 2000: 2, 2001: 4}))

    found = by_key(con, "FROM league_strength()", "season")

    assert found[2000]["talent_z"] > found[1999]["talent_z"]
    assert found[2001]["talent_z"] < found[2000]["talent_z"]


def test_in_context_wins_are_bpm_over_replacement_times_minute_share_and_wins_per_point() -> None:
    con = lake(League())

    found = by_key(con, "FROM era_wins_season()", "season", "player_id")

    star = found[(2000, STAR)]
    assert star["minute_share"] == pytest.approx(3000 / (19680 / 5))
    assert star["wins"] == pytest.approx((5 + 2) * star["minute_share"] * 1.8)


def test_the_whistle_adjustment_is_zero_in_the_reference_season_and_nets_to_zero_by_minutes() -> (
    None
):
    con = lake(League(two_trips={1999: 4, 2000: 2, 2001: 2}))

    found = by_key(con, "FROM era_wins_season(reference_season := 2001)", "season", "player_id")

    assert found[(2001, STAR)]["whistle_adj"] == pytest.approx(0)
    assert found[(2001, ROLE)]["whistle_adj"] == pytest.approx(0)
    assert found[(1999, STAR)]["whistle_adj"] < 0
    assert found[(1999, ROLE)]["whistle_adj"] > 0
    net = sum(found[(1999, p)]["whistle_adj"] * found[(1999, p)]["mp"] for p in (STAR, ROLE))
    assert net == pytest.approx(0)


def test_neutral_bpm_adds_whistle_and_strength_and_uses_reference_wins_per_point() -> None:
    con = lake(League(two_trips={1999: 4, 2000: 2, 2001: 2}))

    found = rows(con, "FROM era_wins_season(reference_season := 2001)")

    for r in found:
        assert r["neutral_bpm"] == pytest.approx(r["bpm"] + r["whistle_adj"] + r["strength"])
        assert r["neutral_wins"] == pytest.approx((r["neutral_bpm"] + 2) * r["minute_share"] * 1.8)


def test_career_sums_seasons_and_flags_a_career_begun_before_the_seasons_counted() -> None:
    con = lake(League())

    seasons = rows(con, "FROM era_wins_season(reference_season := 2001)")
    found = by_key(con, "FROM career_era_wins(reference_season := 2001)", "player_id")

    star = [r for r in seasons if r["player_id"] == STAR]
    assert found[STAR]["neutral_wins"] == pytest.approx(sum(r["neutral_wins"] for r in star))
    assert found[STAR]["seasons"] == 3
    assert found[STAR]["rank"] == 1
    assert not found[STAR]["partial"]
    assert found[ROLE]["partial"]


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("FROM era_wins_season(first_season := 1970)", "1974 or later"),
        ("FROM free_throw_environment(first_season := 1960)", "1974 or later"),
        ("FROM wins_per_point(half_window := -1)", "0 or more"),
        ("FROM league_strength(min_minutes := 0)", "positive"),
    ],
)
def test_out_of_range_arguments_raise(sql: str, message: str) -> None:
    con = lake(League())

    with pytest.raises(duckdb.Error, match=message):
        con.execute(sql).fetchall()
