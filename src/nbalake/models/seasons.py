from nbalake.models.model import Kind, Model

MODELS: tuple[Model, ...] = (
    Model(
        "recorded_from",
        grain=(
            "lg",
            "stat",
        ),
        kind=Kind.SEED,
        sort=("lg", "stat"),
        description="First season each counting stat carries values per league, measured from "
        "Basketball-Reference. NULL means the league never recorded it.",
    ),
    Model(
        "us_population",
        grain=("year",),
        kind=Kind.SEED,
        sort=("year",),
        description="US resident population plus armed forces overseas on January 1 of each "
        "year from 1952, Census Bureau figures through FRED series POP, fetched 2026-10-24.",
    ),
    Model(
        "player_seasons",
        grain=(
            "season",
            "lg",
            "player_id",
            "bref_team",
        ),
        sort=("season", "player_id", "bref_team"),
        description="One row per player, league, season, and team from Basketball-Reference "
        "totals, advanced, per 100, shooting, and play-by-play, regular season only. Multi-team "
        "rows have no team_id.",
    ),
    Model(
        "team_season_stats",
        grain=(
            "season",
            "team_id",
        ),
        sort=("season", "team_id"),
        description="Basketball-Reference team totals, per 100, and opponent stats per season.",
    ),
    Model(
        "raptor",
        grain=(
            "season",
            "bref_id",
            "model",
        ),
        sort=("season", "bref_id"),
        description="FiveThirtyEight RAPTOR, modern and historical, with canonical player_id.",
    ),
    Model(
        "player_impact",
        grain=("season", "season_type", "player_id"),
        sort=("season", "season_type", "player_id"),
        description="sportsdataverse's own impact models per player season from 1996-97: "
        "single-season RAPM, adjusted RAPM with an SPM prior, SPM, BPM 2.0, WAR, and a DARKO "
        "forecast of the next season. These are hoopR reimplementations, not the published "
        "Basketball-Reference or DARKO numbers. primary_team_id is the team he played the most "
        "games for, and teams lists every team by games.",
    ),
    Model(
        "awards",
        grain=(
            "season",
            "award",
            "bref_id",
        ),
        sort=("season", "award", "bref_id"),
        description="Award voting, All-Star selections, and All-League teams by player_id.",
    ),
    Model(
        "player_season_dash",
        grain=("season", "season_type", "player_id"),
        sort=("season", "season_type", "player_id"),
        description="NBA Stats leaguedash season totals per player from 1996-97, regular season "
        "and playoffs: the base, advanced, misc, scoring, usage, and defense measures in one row, "
        "ranks dropped. One row per player season on the player's last team, last_team_id, "
        "with team_count teams.",
    ),
    Model(
        "team_season_dash",
        grain=("season", "season_type", "team_id"),
        sort=("season", "season_type", "team_id"),
        description="NBA Stats leaguedash season totals per team from 1996-97: base, advanced, "
        "misc, scoring, defense, four factors, and opponent measures in one row, ranks dropped.",
    ),
    Model(
        "player_season_tracking",
        grain=("season", "season_type", "player_id"),
        sort=("season", "season_type", "player_id"),
        description="NBA Stats player tracking season totals from 2013-14: drives, catch and "
        "shoot, pull-ups, elbow, post, and paint touches, passing, possessions, speed and "
        "distance, rebounding, defense, and efficiency in one row. One row per player season "
        "on the last team, last_team_id.",
    ),
    Model(
        "player_season_hustle",
        grain=("season", "season_type", "player_id"),
        sort=("season", "season_type", "player_id"),
        description="NBA Stats hustle season totals per player from 2015-16: contested shots, "
        "deflections, charges drawn, screen assists, loose balls, and box outs. One row per "
        "player season on the last team, last_team_id.",
    ),
    Model(
        "team_season_hustle",
        grain=("season", "season_type", "team_id"),
        sort=("season", "season_type", "team_id"),
        description="NBA Stats hustle season totals per team from 2015-16.",
    ),
    Model(
        "player_season_closest_defender",
        grain=("season", "season_type", "player_id", "defender_distance"),
        sort=("season", "season_type", "player_id", "defender_ft_min"),
        description="NBA Stats shooting by closest defender distance per player season from "
        "2013-14: attempts and makes, two and three, in four bands, very_tight 0-2 ft, tight "
        "2-4, open 4-6, and wide_open 6 ft or more. One row per player season and band on the "
        "last team, last_team_id.",
    ),
    Model(
        "team_season_closest_defender",
        grain=("season", "season_type", "team_id", "side", "defender_distance"),
        sort=("season", "season_type", "team_id", "side", "defender_ft_min"),
        description="NBA Stats shooting by closest defender distance per team season from "
        "2013-14 in the same four bands. side offense is the team's own shots, defense the "
        "shots it allowed.",
    ),
    Model(
        "player_season_play_types",
        grain=("season", "season_type", "side", "play_type", "player_id", "team_id"),
        sort=("season", "season_type", "player_id", "side", "play_type"),
        description="Synergy play types per player, team, and side from 2015-16: possessions, "
        "points per possession, percentile, and shooting by play type. side is offense or "
        "defense. A traded player has a row per team.",
    ),
    Model(
        "matchups_game",
        grain=("game_id", "off_player_id", "def_player_id"),
        sort=("season", "game_id", "off_player_id", "def_player_id"),
        description="NBA Stats box score matchups from 2017-18: each offensive player against "
        "each defender who guarded him in a game, with partial possessions, matchup seconds, "
        "switches, and the points, shots, and assists in the matchup.",
    ),
    Model(
        "matchups_season",
        grain=("season", "season_type", "off_player_id", "def_player_id"),
        sort=("season", "off_player_id", "def_player_id"),
        description="NBA Stats season matchup totals from 2017-18, regular season only: each "
        "offensive player against each defender over the season.",
    ),
)
