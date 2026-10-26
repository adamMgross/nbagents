"""shufinskiy/nba_data: play-by-play and shot archives, one tar.xz per season and season type."""

from nbalake.model import Csv, Dataset, GitDir

REPO = "shufinskiy/nba_data"
PATH = "datasets"


def season_columns(groups: dict[str, str]) -> dict[str, object]:
    return {
        "season": int(groups["start"]) + 1,
        "season_type": "playoffs" if groups["po"] else "regular",
    }


def archive(
    name: str,
    sort: tuple[str, ...],
    description: str,
    types: tuple[tuple[str, str], ...] = (),
    partition: str | None = None,
) -> Dataset:
    return Dataset(
        f"shuf.{name}",
        GitDir(REPO, PATH, rf"{name}_(?P<po>po_)?(?P<start>\d{{4}})\.tar\.xz"),
        parse=Csv(),
        partition=partition,
        sort=sort if partition else ("season", *sort),
        types=types,
        unit_columns=season_columns,
        description=description,
    )


DATASETS: tuple[Dataset, ...] = (
    archive(
        "nbastats",
        ("GAME_ID", "EVENTNUM"),
        "stats.nba.com play-by-play v2, 1996-97 on.",
        partition="season",
    ),
    archive(
        "nbastatsv3",
        ("gameId", "actionNumber"),
        "stats.nba.com play-by-play v3 actions.",
        partition="season",
    ),
    archive(
        "datanba",
        ("GAME_ID", "evt"),
        "data.nba.com play-by-play with event coordinates, 2016-17 on.",
        types=(("wallclk", "VARCHAR"),),
    ),
    archive(
        "cdnnba",
        ("gameId", "actionNumber"),
        "cdn.nba.com play-by-play with qualifiers and wall clock, 2019-20 on.",
    ),
    archive(
        "pbpstats",
        ("GAMEID", "PERIOD"),
        "pbpstats.com possessions with start type and event text, 2000-01 on.",
        partition="season",
    ),
    archive(
        "shotdetail", ("GAME_ID", "GAME_EVENT_ID"), "stats.nba.com shot chart detail, 1996-97 on."
    ),
    archive(
        "matchups",
        ("game_id", "team_id", "person_id", "matchups_person_id"),
        "stats.nba.com box score matchups per game, 2017-18 on.",
    ),
)
