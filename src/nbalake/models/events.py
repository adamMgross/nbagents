from nbalake.models.model import Chunk, Kind, Model

BY_SEASON = Chunk("season", "sdv.nba_stats_pbp")

MODELS: tuple[Model, ...] = (
    Model(
        "pbp_actors",
        grain=("game_id", "action_number"),
        sort=("season", "game_id", "action_number"),
        chunk=BY_SEASON,
        description="The second player on a play-by-play action: the assister on a make from "
        "1996-97, the blocker on a miss, the stealer on a turnover, and the fouled player on a "
        "foul from 2005-06. Blocks and steals come from NBA Stats v3, assists and fouled players "
        "from the v2 copy in shuf.nbastats through 2024-25 and from cdn.nba.com in 2025-26, "
        "regular season and playoff games only.",
    ),
    Model(
        "pbp_qualifiers",
        grain=("game_id", "action_number"),
        sort=("season", "game_id", "action_number"),
        chunk=Chunk("season", "shuf.cdnnba"),
        description="cdn.nba.com play-by-play detail from 2020-21 through 2025-26, regular "
        "season and playoffs: the qualifier list with fast_break, second_chance, from_turnover, "
        "and points_in_paint flags, the shot or foul descriptor, the official on a foul, and the "
        "wall clock.",
    ),
    Model(
        "pbp",
        grain=("game_id", "order_index"),
        partition="season",
        sort=("game_id", "order_index"),
        chunk=BY_SEASON,
        description="NBA Stats play-by-play from 1996-97 with every source column, integer scores, "
        "game seconds elapsed, and a garbage_time flag: fourth period or later with a margin "
        "before the event of 30, of 25 inside nine minutes, or of 20 inside six. player_id is "
        "NULL for team events and also carries coach and referee ids. The assist, block, steal, "
        "and fouled player ids from pbp_actors sit on the primary action, never on the "
        "separate block and steal rows whose action_type is empty.",
    ),
    Model(
        "possessions",
        kind=Kind.VIEW,
        description="NBA Stats possessions with offense, defense, points, and both lineups. "
        "Points run about 1.5 per team-game under the box score before 2017-18 and about "
        "0.15 under after, so the box score is the scoring source.",
    ),
    Model(
        "shots",
        kind=Kind.VIEW,
        description="NBA Stats shot chart with made as a boolean and court coordinates in feet.",
    ),
    Model(
        "lineup_stints",
        kind=Kind.VIEW,
        description="The ten players on the floor at every play-by-play action.",
    ),
    Model(
        "pbp_espn",
        kind=Kind.VIEW,
        description="ESPN play-by-play with the canonical game_id and missing coordinates as NULL.",
    ),
)
