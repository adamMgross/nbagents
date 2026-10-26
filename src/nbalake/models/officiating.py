from nbalake.models.model import Model

MODELS: tuple[Model, ...] = (
    Model(
        "game_officials",
        grain=("game_id", "official_id"),
        sort=("season", "game_id", "official_id"),
        description="The referees NBA Stats lists for each game from 1996-97, three a game and "
        "four in some playoff games. Join pbp fouls or l2m_calls on game_id for the crew.",
    ),
    Model(
        "officials",
        grain=("official_id",),
        sort=("official_id",),
        description="One row per NBA Stats official with the latest name, the first and last "
        "season worked, and games.",
    ),
    Model(
        "l2m_calls",
        grain=(
            "game_id",
            "period",
            "call_id",
        ),
        sort=("season", "game_id", "period", "call_id"),
        description="Every graded call in the NBA Last Two Minute reports from 2014-15, with "
        "players resolved against the game's box score and the method that resolved them.",
    ),
    Model(
        "l2m_games",
        grain=("game_id",),
        sort=("game_id",),
        description="One row per Last Two Minute report with call counts by decision.",
    ),
)
