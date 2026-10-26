from nbalake.models.model import Kind, Model

MODELS: tuple[Model, ...] = (
    Model(
        "arenas",
        kind=Kind.SEED,
        grain=("arena", "team_id"),
        sort=("arena", "team_id"),
        description="Coordinates from Wikidata for every arena Basketball-Reference names as a "
        "team's home and every neutral site ESPN names. team_id is set only where one name "
        "means different buildings for different teams.",
    ),
    Model(
        "games",
        grain=("game_id",),
        sort=("season", "game_date", "game_id"),
        description="One row per played game from 1946-47, NBA Stats from 1996-97 and "
        "FiveThirtyEight before, with ESPN and FiveThirtyEight ids, venue, and attendance where "
        "known. A completed ESPN game newer than every NBA Stats game has source espn and the "
        "minted game_id 'espn' plus the ESPN id until NBA Stats publishes it. home_team_name and "
        "away_team_name are the names the teams used that season.",
    ),
    Model(
        "game_xref",
        kind=Kind.VIEW,
        description="Every NBA Stats, ESPN, FiveThirtyEight, and minted game id mapped to the "
        "current game_id, so a minted id saved before NBA Stats published the game still resolves.",
    ),
    Model(
        "team_elo",
        grain=("game_id", "team_id"),
        sort=("season", "game_id", "team_id"),
        description="The lake's own Elo for every regular, play-in, playoff, and Cup game from "
        "2014-15, FiveThirtyEight's method continued from their ratings at the end of 2013-14, "
        "and fit_* beside it with the home edge fitted to the previous three seasons. 2014-15 "
        "overlaps FiveThirtyEight as a check.",
    ),
    Model(
        "team_games",
        grain=(
            "game_id",
            "team_id",
        ),
        sort=("season", "game_date", "game_id", "team_id"),
        description="Two rows per game, one per team, with result, Elo, rest days, back to backs, "
        "games in the previous seven days, and kilometers traveled since the last game. "
        "team_name and opponent_name are that season's.",
    ),
    Model(
        "playoff_series",
        grain=("series_id",),
        sort=("season", "lg", "round", "series_id"),
        description="One row per playoff series from 1946-47, NBA, BAA, and ABA brackets apart, "
        "with the league round, format, home court, wins, games in order, each team's Elo "
        "entering the series, the Elo chance the home-court team wins it, and next_series_id, "
        "the series its winner plays next. Tiebreaker games are not series. Seasons whose "
        "games do not form an elimination bracket are left out.",
    ),
    Model(
        "games_cross_source",
        grain=(
            "issue",
            "season",
            "source_id",
        ),
        sort=("issue", "season", "source_id"),
        description="Games where NBA Stats, ESPN, and FiveThirtyEight fail to match or disagree.",
    ),
)
