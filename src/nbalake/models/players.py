from nbalake.models.model import Kind, Model

MODELS: tuple[Model, ...] = (
    Model(
        "player_birthplaces",
        kind=Kind.SEED,
        grain=("bref_id",),
        sort=("bref_id",),
        description="Birth country per Basketball-Reference slug from Wikidata, fetched "
        "2026-10-24: born_in_us, and every country Wikidata gives the birthplace, NULL where "
        "Wikidata has no birthplace.",
    ),
    Model(
        "espn_bref_links",
        kind=Kind.SEED,
        grain=("espn_id",),
        sort=("espn_id",),
        description="Hand links from ESPN athlete ids to Basketball-Reference slugs for players "
        "whose ESPN name no rule matches, such as Tyrone Bogues for Muggsy Bogues.",
    ),
    Model(
        "player_xref",
        grain=(
            "source",
            "source_id",
        ),
        sort=("source", "source_id"),
        description="Every NBA Stats, Basketball-Reference, ESPN, and FiveThirtyEight player id "
        "mapped to one canonical player_id, with the matching method and the source's span.",
    ),
    Model(
        "players",
        grain=("player_id",),
        sort=("player_id",),
        description="One row per canonical player with bio, draft, career span, and source ids. "
        "Players without an NBA Stats id carry a minted id of 9000000000000 and up.",
    ),
    Model(
        "unresolved_players",
        grain=(
            "source",
            "source_id",
        ),
        sort=("source", "source_id"),
        description="ESPN and FiveThirtyEight player ids that matched no canonical player.",
    ),
    Model(
        "draft_combine",
        grain=("season", "player_id"),
        sort=("season", "player_id"),
        description="NBA draft combine results from the 2001 combine: measurements, drills, and "
        "spot and on-the-move shooting, one row per prospect per combine. season is the rookie "
        "season the combine leads into, so the May 2003 combine is 2004. player_id is the NBA "
        "Stats id, kept for prospects who never played, and played says who did (decision 24).",
    ),
    Model(
        "injuries",
        grain=("snapshot_date", "espn_athlete_id"),
        sort=("snapshot_date", "team_id", "espn_athlete_id"),
        description="ESPN's injury report, one row per listed player per daily snapshot from "
        "2026-09-08, with status, the injury, the expected return, and the report text. "
        "snapshot_date is ESPN's as_of_date, and a player absent from a snapshot was not listed.",
    ),
    Model(
        "injuries_latest",
        kind=Kind.VIEW,
        description="The newest snapshot of nba.injuries: who is injured now.",
    ),
    Model(
        "depth_charts",
        grain=("snapshot_date", "espn_team_id", "position", "depth_rank"),
        sort=("snapshot_date", "team_id", "position", "depth_rank"),
        description="ESPN's depth charts, one row per team, position, and rank per daily "
        "snapshot from 2026-09-08. depth_rank 1 is the starter at that position.",
    ),
    Model(
        "depth_charts_latest",
        kind=Kind.VIEW,
        description="The newest snapshot of nba.depth_charts.",
    ),
)
