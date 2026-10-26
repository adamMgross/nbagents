from nbalake.model import Csv, Dataset, GitDir

REPO = "fivethirtyeight/data"


def file(path: str, name: str) -> GitDir:
    return GitDir(REPO, path, name.replace(".", r"\."), ref="master")


DATASETS: tuple[Dataset, ...] = (
    Dataset(
        "fte.elo",
        file("nba-elo", "nbaallelo.csv"),
        parse=Csv(),
        sort=("gameorder", "_iscopy"),
        description="FiveThirtyEight Elo per team-game, 1946-47 through 2014-15.",
    ),
    Dataset(
        "fte.raptor_player_modern",
        file("nba-raptor", "modern_RAPTOR_by_player.csv"),
        parse=Csv(),
        sort=("season", "player_id"),
        description="RAPTOR by player and season, modern era with tracking data.",
    ),
    Dataset(
        "fte.raptor_player_historical",
        file("nba-raptor", "historical_RAPTOR_by_player.csv"),
        parse=Csv(),
        sort=("season", "player_id"),
        description="RAPTOR by player and season, box-score-only historical model.",
    ),
    Dataset(
        "fte.raptor_team_modern",
        file("nba-raptor", "modern_RAPTOR_by_team.csv"),
        parse=Csv(),
        sort=("season", "player_id", "team"),
        description="RAPTOR by player, team, and season, modern era.",
    ),
    Dataset(
        "fte.raptor_team_historical",
        file("nba-raptor", "historical_RAPTOR_by_team.csv"),
        parse=Csv(),
        sort=("season", "player_id", "team"),
        description="RAPTOR by player, team, and season, historical model.",
    ),
)
