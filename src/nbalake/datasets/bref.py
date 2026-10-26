"""Kaggle mirror of Basketball-Reference season tables (sumitrodatta), BAA, NBA, and ABA."""

from nbalake.model import Csv, Dataset, Kaggle

DUMP = Kaggle("sumitrodatta", "nba-aba-baa-stats")
NULLS = ("", "NA")

PLAYER_SEASON = ("season", "player_id", "team")
TEAM_SEASON = ("season", "team")


def table(name: str, member: str, sort: tuple[str, ...], description: str) -> Dataset:
    return Dataset(
        f"bref.{name}",
        DUMP,
        parse=Csv(member=member, nulls=NULLS),
        sort=sort,
        description=description,
    )


DATASETS: tuple[Dataset, ...] = (
    table(
        "player_totals",
        "Player Totals.csv",
        PLAYER_SEASON,
        "Season totals per player and team. Regular season only.",
    ),
    table(
        "player_per_game",
        "Player Per Game.csv",
        PLAYER_SEASON,
        "Per-game averages per player and team. Regular season only.",
    ),
    table(
        "player_per_36",
        "Per 36 Minutes.csv",
        PLAYER_SEASON,
        "Per 36 minute rates per player and team. Regular season only.",
    ),
    table(
        "player_per_100",
        "Per 100 Poss.csv",
        PLAYER_SEASON,
        "Per 100 possession rates per player and team, 1973-74 on. Regular season only.",
    ),
    table(
        "player_advanced",
        "Advanced.csv",
        PLAYER_SEASON,
        "PER, true shooting, win shares, BPM, and VORP per player season. Regular season only.",
    ),
    table(
        "player_shooting",
        "Player Shooting.csv",
        PLAYER_SEASON,
        "Shot distance and type splits per player season. Regular season only.",
    ),
    table(
        "player_play_by_play",
        "Player Play By Play.csv",
        PLAYER_SEASON,
        "Position estimates, on-off, and fouls drawn per player season. Regular season only.",
    ),
    table(
        "player_season_info",
        "Player Season Info.csv",
        PLAYER_SEASON,
        "One row per player season: age, team, position, experience.",
    ),
    table(
        "player_career_info",
        "Player Career Info.csv",
        ("player_id",),
        "One row per player: height, weight, birth date, colleges, career span, Hall of Fame.",
    ),
    table(
        "player_award_shares",
        "Player Award Shares.csv",
        ("season", "award", "player_id"),
        "Award voting shares per player season.",
    ),
    table(
        "all_star_selections",
        "All-Star Selections.csv",
        ("season", "player"),
        "All-Star selections.",
    ),
    table(
        "end_of_season_teams",
        "End of Season Teams.csv",
        ("season", "type", "player_id"),
        "All-NBA, All-Defensive, and All-Rookie selections.",
    ),
    table(
        "end_of_season_teams_voting",
        "End of Season Teams (Voting).csv",
        ("season", "type", "player_id"),
        "Voting detail for end of season teams.",
    ),
    table(
        "draft_pick_history",
        "Draft Pick History.csv",
        ("season", "overall_pick"),
        "Draft picks with career outcomes.",
    ),
    table("team_totals", "Team Totals.csv", TEAM_SEASON, "Team season totals."),
    table("team_per_game", "Team Stats Per Game.csv", TEAM_SEASON, "Team per-game averages."),
    table(
        "team_per_100",
        "Team Stats Per 100 Poss.csv",
        TEAM_SEASON,
        "Team per 100 possession rates, 1973-74 on.",
    ),
    table(
        "team_summaries",
        "Team Summaries.csv",
        TEAM_SEASON,
        "Team season summaries: record, ratings, pace, four factors, arena, attendance.",
    ),
    table(
        "opponent_totals", "Opponent Totals.csv", TEAM_SEASON, "Opponent season totals per team."
    ),
    table(
        "opponent_per_game",
        "Opponent Stats Per Game.csv",
        TEAM_SEASON,
        "Opponent per-game averages per team.",
    ),
    table(
        "opponent_per_100",
        "Opponent Stats Per 100 Poss.csv",
        TEAM_SEASON,
        "Opponent per 100 possession rates per team.",
    ),
    table(
        "team_abbrev",
        "Team Abbrev.csv",
        ("season", "abbreviation"),
        "Team name to abbreviation per season.",
    ),
)
