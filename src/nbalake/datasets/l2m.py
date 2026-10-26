from nbalake.model import Csv, Dataset, GitDir

DIR = "1-tidy/L2M"

DATASETS: tuple[Dataset, ...] = (
    Dataset(
        "l2m.calls",
        GitDir("atlhawksfanatic/L2M", DIR, r"L2M_stats_nba\.csv", ref="master"),
        parse=Csv(nulls=("", "NA")),
        sort=("season", "game_id", "period", "time"),
        description="Every graded call in the NBA Last Two Minute reports, with NBA Stats ids.",
    ),
    Dataset(
        "l2m.teams",
        GitDir("atlhawksfanatic/L2M", DIR, r"team_ids\.csv", ref="master"),
        parse=Csv(nulls=("", "NA")),
        sort=("teamId",),
        description="Team id lookup used by the L2M tidy data.",
    ),
)
