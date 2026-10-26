from nbalake.models.model import Kind, Model

MODELS: tuple[Model, ...] = (
    Model(
        "odds_teams",
        grain=("code",),
        kind=Kind.SEED,
        sort=("code",),
        description="The current franchise codes that odds.lines uses for every season, mapped "
        "to team_id.",
    ),
    Model(
        "game_lines",
        grain=(
            "game_id",
            "source",
            "book",
        ),
        sort=("game_id", "source", "book"),
        description="Betting lines per game, source, and sportsbook. home_spread is the points "
        "added to the home score, so negative means the home team is favored. Moneylines and "
        "prices are American odds. kaggle_lines has one line per game from 2007-08, "
        "kaggle_books has ten sportsbooks for 2006-07 to 2017-18 with book set, and espn has "
        "spreads only from 2012-13.",
    ),
)
