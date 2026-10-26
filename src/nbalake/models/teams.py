from nbalake.models.model import Kind, Model

MODELS: tuple[Model, ...] = (
    Model(
        "franchises",
        grain=("code",),
        kind=Kind.SEED,
        sort=("team_id", "code"),
        description="Every Basketball-Reference and FiveThirtyEight team code mapped to one "
        "canonical team_id. Defunct franchises use 800000001 onward.",
    ),
    Model(
        "team_seasons",
        grain=(
            "season",
            "team_id",
        ),
        sort=("season", "team_id"),
        description="One row per franchise season from 1947 with league, codes, conference, "
        "division, ESPN id, and the Basketball-Reference season summary.",
    ),
    Model(
        "teams",
        grain=("team_id",),
        sort=("team_id",),
        description="One row per franchise with its current or final name and season span.",
    ),
)
