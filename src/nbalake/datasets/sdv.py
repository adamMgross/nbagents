"""sportsdataverse-data releases: nightly Parquet mirrors of NBA Stats and ESPN."""

from nbalake.model import Dataset, ReleaseAssets, Versions

SEASON = r"_(?P<season>\d{4})\.parquet"


def season_first(sort: tuple[str, ...]) -> tuple[str, ...]:
    return ("season", *(c for c in sort if c != "season"))


def per_season(
    name: str,
    tag: str,
    stem: str,
    *,
    partition: str | None = None,
    sort: tuple[str, ...] = (),
    versions: Versions = Versions.LATEST,
    description: str = "",
) -> Dataset:
    return Dataset(
        f"sdv.{name}",
        ReleaseAssets(tag, stem + SEASON),
        partition=partition,
        sort=sort if partition else season_first(sort),
        versions=versions,
        description=description,
    )


def single(
    name: str, tag: str, file: str, *, sort: tuple[str, ...] = (), description: str = ""
) -> Dataset:
    return Dataset(
        f"sdv.{name}",
        ReleaseAssets(tag, file.replace(".", r"\.")),
        sort=sort,
        description=description,
    )


def faceted(
    name: str,
    tag: str,
    pattern: str,
    *,
    sort: tuple[str, ...] = (),
    types: tuple[tuple[str, str], ...] = (),
    description: str = "",
) -> Dataset:
    """Several upstream files per season, distinguished by named groups that become columns."""
    return Dataset(
        f"sdv.{name}",
        ReleaseAssets(tag, pattern + SEASON),
        sort=season_first(sort),
        types=types,
        description=description,
    )


SEASON_TYPE = r"(?P<season_type>regular-season|playoffs)"
PER_MODE = r"(?P<per_mode>totals|pergame)"

DRAFT_COMBINE = {
    "stats": "measurements and results summary",
    "playeranthro": "anthropometrics",
    "drillresults": "athletic drill results",
    "spotshooting": "spot-up shooting",
    "nonstationaryshooting": "shooting off movement",
}

LEAGUEDASH_SORT = {
    "player": ("season", "season_type", "player_id"),
    "team": ("season", "season_type", "team_id"),
    "lineups": ("season", "season_type", "group_id"),
    "standings": ("season", "season_type", "team_id"),
}

LEAGUEDASH = (
    "player_master",
    "player_bio",
    "player_stats_base",
    "player_stats_advanced",
    "player_stats_misc",
    "player_stats_scoring",
    "player_stats_usage",
    "player_stats_defense",
    "player_tracking_catchshoot",
    "player_tracking_pullupshot",
    "player_tracking_defense",
    "player_tracking_drives",
    "player_tracking_efficiency",
    "player_tracking_elbowtouch",
    "player_tracking_painttouch",
    "player_tracking_posttouch",
    "player_tracking_passing",
    "player_tracking_possessions",
    "player_tracking_rebounding",
    "player_tracking_speeddistance",
    "team_master",
    "team_stats_base",
    "team_stats_advanced",
    "team_stats_misc",
    "team_stats_scoring",
    "team_stats_defense",
    "team_stats_fourfactors",
    "team_stats_opponent",
    "lineups_master",
    "lineups_base",
    "lineups_advanced",
    "lineups_misc",
    "lineups_scoring",
    "lineups_fourfactors",
    "lineups_opponent",
    "standings",
)

NBA_STATS_GAMES = (
    per_season(
        "nba_stats_schedules",
        "nba_stats_schedules",
        "nba_schedule",
        sort=("game_date", "game_id"),
        description="NBA Stats schedule and final scores, one row per game.",
    ),
    per_season(
        "nba_stats_team_boxscores",
        "nba_stats_team_boxscores",
        "team_boxscores",
        sort=("game_id", "team_id"),
        description="NBA Stats traditional team box scores.",
    ),
    per_season(
        "nba_stats_player_boxscores",
        "nba_stats_player_boxscores",
        "player_boxscores",
        sort=("game_id", "team_id", "person_id"),
        description="NBA Stats traditional player box scores.",
    ),
    per_season(
        "nba_stats_player_game_logs",
        "nba_stats_player_game_logs",
        "player_game_logs",
        sort=("game_id", "team_id"),
        description="NBA Stats team game logs, one row per team and game (upstream name misleads).",
    ),
    per_season(
        "nba_stats_pbp",
        "nba_stats_pbp",
        "nba_play_by_play",
        partition="season",
        sort=("game_id", "order_index"),
        description="NBA Stats play-by-play (v3 actions) with on-court lineups.",
    ),
    per_season(
        "nba_stats_possessions",
        "nba_stats_possessions",
        "nba_possessions",
        description="Possessions derived from NBA Stats play-by-play.",
    ),
    per_season(
        "nba_stats_shots",
        "nba_stats_shots",
        "shots",
        description="NBA Stats shot chart detail with court coordinates.",
    ),
    per_season(
        "nba_stats_game_lineups",
        "nba_stats_game_lineups",
        "nba_lineups",
        description="Five-man lineup stints per game.",
    ),
    per_season(
        "nba_stats_game_rosters",
        "nba_stats_game_rosters",
        "game_rosters",
        sort=("game_id", "team_id", "player_id"),
        description="Inactive players per game, despite the upstream name.",
    ),
    per_season(
        "nba_stats_game_matchups",
        "nba_stats_game_matchups",
        "game_matchups",
        sort=("game_id", "off_person_id", "def_person_id"),
        description="Player-vs-player matchup minutes and results per game.",
    ),
    per_season(
        "nba_stats_officials",
        "nba_stats_officials",
        "officials",
        sort=("game_id", "official_id"),
        description="Officials assigned per game.",
    ),
)

NBA_STATS_SEASONS = (
    per_season(
        "nba_stats_player_season_stats",
        "nba_stats_player_season_stats",
        "player_season_stats",
        description="NBA Stats player season totals and rates.",
    ),
    per_season(
        "nba_stats_team_season_stats",
        "nba_stats_team_season_stats",
        "team_season_stats",
        description="NBA Stats team season totals and rates.",
    ),
    per_season(
        "nba_stats_standings",
        "nba_stats_standings",
        "standings",
        description="Final and in-season standings.",
    ),
    per_season("nba_stats_rosters", "nba_stats_rosters", "rosters", description="Season rosters."),
    per_season(
        "nba_stats_coaches",
        "nba_stats_coaches",
        "coaches",
        description="Coaching staffs per team and season.",
    ),
    per_season(
        "nba_stats_draft", "nba_stats_draft", "draft", description="Draft picks per season."
    ),
    per_season(
        "nba_stats_lineups", "nba_stats_lineups", "lineups", description="Season lineup aggregates."
    ),
    per_season(
        "nba_stats_metric_curves",
        "nba_stats_metric_curves",
        "metric_curves",
        description="League-wide metric distribution curves per season.",
    ),
    per_season(
        "nba_stats_rolling_windows",
        "nba_stats_rolling_windows",
        "rolling_windows",
        description="Rolling-window team and player aggregates.",
    ),
    per_season(
        "nba_player_impact",
        "nba_player_impact",
        "nba_player_impact",
        description="sportsdataverse player impact estimates per season.",
    ),
    faceted(
        "nba_stats_synergy",
        "nba_stats_synergy",
        rf"{SEASON_TYPE}_(?P<play_type>\w+?)_(?P<side>offensive|defensive)_{PER_MODE}",
        description="Synergy play type stats by season type, play type, side, and per mode.",
    ),
    faceted(
        "hustle_player",
        "nba_stats_hustle",
        rf"leaguehustlestatsplayer_{SEASON_TYPE}_{PER_MODE}",
        description="Hustle stats per player, by season type and per mode.",
    ),
    faceted(
        "hustle_team",
        "nba_stats_hustle",
        rf"leaguehustlestatsteam_{SEASON_TYPE}_{PER_MODE}",
        description="Hustle stats per team, by season type and per mode.",
    ),
    faceted(
        "season_matchups",
        "nba_stats_matchups",
        rf"leagueseasonmatchups_{SEASON_TYPE}_{PER_MODE}",
        types=(("matchup_min", "VARCHAR"),),
        description="Season-long player-vs-player matchup aggregates.",
    ),
    faceted(
        "matchups_rollup",
        "nba_stats_matchups",
        rf"matchupsrollup_{SEASON_TYPE}_{PER_MODE}",
        types=(("matchup_min", "VARCHAR"),),
        description="Matchup rollups by defender position group.",
    ),
    *(
        per_season(
            f"draft_combine_{table}",
            "nba_stats_draft_combine",
            f"draftcombine{table}",
            description=f"Draft combine {DRAFT_COMBINE[table]}, one row per prospect and year.",
        )
        for table in DRAFT_COMBINE
    ),
    *(
        per_season(
            f"leaguedash_{table}",
            "nba_stats_leaguedash",
            table,
            sort=LEAGUEDASH_SORT[table.split("_")[0]],
            description=f"League dashboard {table.replace('_', ' ')} per season.",
        )
        for table in LEAGUEDASH
    ),
)

ESPN = (
    per_season(
        "espn_nba_schedules",
        "espn_nba_schedules",
        "nba_schedule",
        sort=("game_date", "game_id"),
        description="ESPN schedule with venues, broadcasts, and status, one row per game.",
    ),
    single(
        "espn_nba_schedule_master",
        "espn_nba_schedules",
        "nba_schedule_master.parquet",
        sort=("game_date", "game_id"),
        description="ESPN master schedule across all seasons.",
    ),
    single(
        "espn_nba_games_in_data_repo",
        "espn_nba_schedules",
        "nba_games_in_data_repo.parquet",
        sort=("game_date", "game_id"),
        description="ESPN games with play-by-play and box score availability flags.",
    ),
    per_season(
        "espn_nba_pbp",
        "espn_nba_pbp",
        "play_by_play",
        partition="season",
        sort=("game_id", "game_play_number"),
        description="ESPN play-by-play with coordinates and win probability context.",
    ),
    per_season("espn_nba_shots", "espn_nba_shots", "shots", description="ESPN shot locations."),
    per_season(
        "espn_nba_player_boxscores",
        "espn_nba_player_boxscores",
        "player_box",
        description="ESPN player box scores, 1993-94 on.",
    ),
    per_season(
        "espn_nba_team_boxscores",
        "espn_nba_team_boxscores",
        "team_box",
        description="ESPN team box scores, 1993-94 on.",
    ),
    per_season(
        "espn_nba_game_rosters",
        "espn_nba_game_rosters",
        "game_rosters",
        description="ESPN game rosters.",
    ),
    per_season(
        "espn_nba_officials",
        "espn_nba_officials",
        "officials",
        description="ESPN officials per game.",
    ),
    per_season(
        "espn_nba_player_core",
        "espn_nba_player_core",
        "player_core",
        description="ESPN player biographical core.",
    ),
    per_season(
        "espn_nba_player_season_stats",
        "espn_nba_player_season_stats",
        "player_season_stats",
        description="ESPN player season stats.",
    ),
    per_season(
        "espn_nba_team_season_stats",
        "espn_nba_team_season_stats",
        "team_season_stats",
        description="ESPN team season stats.",
    ),
    per_season(
        "espn_nba_standings", "espn_nba_standings", "standings", description="ESPN standings."
    ),
    per_season("espn_nba_draft", "espn_nba_draft", "draft", description="ESPN draft results."),
    per_season(
        "espn_nba_rosters",
        "espn_nba_rosters",
        "rosters",
        description="ESPN current rosters, recent seasons only.",
    ),
    per_season(
        "espn_nba_injuries",
        "espn_nba_injuries",
        "injuries",
        versions=Versions.ALL,
        description="ESPN injury report. Each nightly capture is kept as its own snapshot.",
    ),
    per_season(
        "espn_nba_depthcharts",
        "espn_nba_depthcharts",
        "depthcharts",
        versions=Versions.ALL,
        description="ESPN depth charts. Each nightly capture is kept as its own snapshot.",
    ),
)

IDENTITY = (
    per_season(
        "nba_player_crosswalk",
        "nba_crosswalk",
        "nba_player_crosswalk",
        sort=("season", "nba_player_id"),
        description="ESPN, NBA Stats, Fox, and Yahoo player ids matched per season.",
    ),
    per_season(
        "nba_team_crosswalk",
        "nba_crosswalk",
        "nba_team_crosswalk",
        sort=("season", "nba_team_id"),
        description="ESPN, NBA Stats, Fox, and Yahoo team ids matched per season.",
    ),
    per_season(
        "nba_schedule_crosswalk",
        "nba_crosswalk",
        "nba_schedule_crosswalk",
        sort=("game_date", "nba_game_id"),
        description="ESPN, NBA Stats, Fox, and Yahoo game ids matched per game.",
    ),
    per_season(
        "nba_team_group_seasons",
        "nba_groups",
        "nba_team_group_seasons",
        description="Team to conference and division membership per season.",
    ),
    single(
        "nba_groups",
        "nba_groups",
        "nba_groups.parquet",
        description="Conference and division groups.",
    ),
    single(
        "nba_group_aliases",
        "nba_groups",
        "nba_group_aliases.parquet",
        description="Aliases for conference and division groups.",
    ),
    single(
        "nba_group_seasons",
        "nba_groups",
        "nba_group_seasons.parquet",
        description="Group membership by season.",
    ),
    single(
        "nba_team_group_seasons_all",
        "nba_groups",
        "nba_team_group_seasons.parquet",
        description="Team group membership across all seasons in one file.",
    ),
)

DATASETS: tuple[Dataset, ...] = (*NBA_STATS_GAMES, *NBA_STATS_SEASONS, *ESPN, *IDENTITY)
