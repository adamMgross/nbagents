from nbalake.models.model import Kind, Model

MODELS: tuple[Model, ...] = (
    Model(
        "caveats",
        kind=Kind.SEED,
        grain=("table_name", "column_name"),
        sort=("table_name", "column_name"),
        description="Known traps per table and column: missing seasons, filler values, and "
        "rows that double count. nba describe shows the ones for its table.",
    ),
    Model(
        "player_aliases",
        kind=Kind.SEED,
        grain=("player_id", "alias"),
        sort=("player_id", "alias"),
        description="Nicknames and alternate names per player_id, like steph or the mailman.",
    ),
    Model(
        "team_aliases",
        kind=Kind.SEED,
        grain=("team_id", "alias"),
        sort=("team_id", "alias"),
        description="Fan names per franchise team_id, like sonics or sixers.",
    ),
    Model(
        "entity_index",
        grain=("kind", "id", "label"),
        sort=("kind", "key"),
        description="Every player, franchise name, and game with a normalized search key, "
        "aliases, seasons, and context. nba find resolves names against it.",
    ),
)
