"""gabriel1200/site_Data: NBA Stats shooting by closest defender distance per season and side."""

from nbalake.model import Csv, Dataset, GitTree

REPO = "gabriel1200/site_Data"
BANDS = "very_tight|tight|open|wide_open"


def unit_columns(groups: dict[str, str]) -> dict[str, object]:
    return {
        "season": int(groups["season"]),
        "season_type": "playoffs" if groups["po"] else "regular",
        "defender_distance": groups["band"],
    }


def by_defender(name: str, folder: str, key: str, description: str) -> Dataset:
    return Dataset(
        f"gab.{name}",
        GitTree(
            REPO,
            rf"(?P<season>\d{{4}})/(?P<po>playoffs/)?{folder}/(?P<band>{BANDS})\.csv",
            ref="master",
        ),
        parse=Csv(nulls=("", "-")),
        sort=("season", "season_type", key, "defender_distance"),
        unit_columns=unit_columns,
        description=description,
    )


DATASETS: tuple[Dataset, ...] = (
    by_defender(
        "player_shots_by_defender",
        "player_shooting",
        "PLAYER_ID",
        "Each player's shots by closest defender distance from 2013-14, NBA Stats tracking.",
    ),
    by_defender(
        "team_shots_by_defender",
        "team_shooting",
        "TEAM",
        "Each team's shots by closest defender distance from 2013-14, NBA Stats tracking.",
    ),
    by_defender(
        "opponent_shots_by_defender",
        "opp_shooting",
        "TEAM",
        "Shots each team allowed by closest defender distance from 2013-14, NBA Stats tracking.",
    ),
)
