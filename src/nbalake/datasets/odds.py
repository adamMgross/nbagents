"""Kaggle mirrors of historical NBA betting lines."""

from nbalake.model import Csv, Dataset, Kaggle

LINES = Kaggle("cviaxmiwnptr", "nba-betting-data-october-2007-to-june-2024")
BOOKS = Kaggle("ehallmar", "nba-historical-stats-and-betting-data")


def book(name: str, member: str, market: str) -> Dataset:
    return Dataset(
        f"odds.{name}",
        BOOKS,
        parse=Csv(member=member, all_varchar=True),
        sort=("game_id", "book_id"),
        description=f"{market} per game and sportsbook, 2006-07 to 2017-18, ten books including "
        "Pinnacle. team_id is the away team. Frozen upstream since 2019.",
    )


DATASETS: tuple[Dataset, ...] = (
    Dataset(
        "odds.lines",
        LINES,
        parse=Csv(),
        sort=("date", "home"),
        description="One spread, total, and moneyline per game from 2007-08, with quarter "
        "scores. Built from Sportsbook Reviews Online through January 2023, which is also when "
        "moneylines end. Team codes are current franchise codes for every season.",
    ),
    book("book_spreads", "nba_betting_spread.csv", "Point spreads and prices"),
    book("book_totals", "nba_betting_totals.csv", "Over/under totals and prices"),
    book("book_moneylines", "nba_betting_money_line.csv", "Moneylines"),
)
