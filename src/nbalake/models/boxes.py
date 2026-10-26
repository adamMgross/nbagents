from nbalake.models.model import Model

MODELS: tuple[Model, ...] = (
    Model(
        "team_box",
        grain=(
            "game_id",
            "team_id",
        ),
        sort=("season", "game_id", "team_id"),
        description="One row per team per game: NBA Stats from 1996-97, ESPN for 1993-94 "
        "through 1995-96. Minutes are seconds.",
    ),
    Model(
        "player_box",
        grain=(
            "game_id",
            "team_id",
            "player_id",
        ),
        sort=("season", "game_id", "team_id", "player_id"),
        description="One row per player per game with canonical player_id, including DNPs "
        "with their reason. Minutes are seconds. started comes from NBA Stats from 2017-18, "
        "and from ESPN game rosters for 2001-02 to 2016-17 where ESPN lists five starters for "
        "the team, and started_source says which.",
    ),
    Model(
        "game_inactives",
        grain=(
            "game_id",
            "team_id",
            "player_id",
        ),
        sort=("season", "game_id", "team_id", "player_id"),
        description="The players NBA Stats lists inactive for each game from 1996-97. About 37 "
        "of them never played a game, so they have no nba.players row.",
    ),
    Model(
        "box_reconciliation",
        grain=(
            "season",
            "game_id",
            "side",
        ),
        sort=("season", "game_id", "side"),
        description="Every game side where the schedule, team box, and player sum disagree, "
        "a box is missing, or a player did not resolve. player_sum_differs compares the player "
        "sum to the team box, or to the schedule score where the team box is missing.",
    ),
)
