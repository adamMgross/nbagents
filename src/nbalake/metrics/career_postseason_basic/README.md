---
name: career_postseason_basic
version: 1
summary: Career postseason achievement from 1958, the career_postseason team credit with rounds counted back from the Finals, split by regular-season win shares so every era is measured the same way.
---

# Basic career postseason achievement

## Question

The question `career_postseason` answers, whose playoff careers achieved
the most, asked across every era from 1957-58 (season 1958) on. Russell,
Chamberlain, West, and Kareem's early years fall before `career_postseason`
starts in 1984. This version gives up playoff minutes so that the 1960s and
today are measured the same way.

## Definition

```
playoff game, per team             per playoff run              sums
------------------------------     -------------------------    ------------
won - baseline_win_prob       ->   team credit for the run  ->  career = run
x round weight from the Finals     x 5 x win share fraction     sum
= postseason_team_credit           = credit
```

1. Team credit per game is `postseason_team_credit`, as in
   `career_postseason`: the win minus the chance the season's weakest
   playoff team wins that game against the same opponent at the same venue.
2. The round weight counts back from the Finals (`rounds := 'from_final'`):
   4 for the Finals, 3 for the round before, and so on. In a four-round
   bracket that is the round number, so from 1975 on it equals
   `career_postseason`'s weight. In the three-round brackets of 1958-74 the
   Finals still weighs 4 and the first round 2. A team with a bye simply
   plays fewer games. During playoffs in progress the bracket is taken to
   have as many rounds as the season before.
3. A run's team credit is the sum over the team's games that postseason.
4. `share` is the player's regular-season win shares over the team's, with
   negative win shares counted as 0. Win shares exist for every season, so
   this split is the same in every era.
5. `credit` is `5 * team_credit * share`, the scale of `career_postseason`.

## Why these choices

Win shares are the only player value the lake has for every season since
the 1950s. BPM starts in 1973-74 and minutes in 1951-52. `from_final`
keeps a 1960s Finals worth what a modern Finals is worth.

The owner's three cases from `career_postseason` still pass:

- Kobe Bryant 2008 keeps 81% of his 2001 run.
- Magic Johnson 1989 ranks 143rd of 14,714 runs, the top 1%.
- LeBron James 2016 ranks 11th.

Against `career_postseason` from 1984, the two agree at a correlation of
0.92 over 9,053 player runs, and 14 of their top 20 careers are shared.

Rejected alternatives:

- `rounds := 'linear'` before 1975, which weighs a three-round Finals 3.
- Starting in 1949. `nba.playoff_series` leaves out 1954, 1956, and 1957,
  so careers spanning them would have holes. 1958 is the first season after
  the last gap.

## Limits

- Shares come from the regular season in every era, so an injured player
  keeps his share of the games he missed, and how anyone played in the
  playoffs never enters. Use `career_postseason` from 1984 for that.
- Win shares add up to a team's wins, so they spread credit to the good
  teammates of stars. Role players on dominant teams rank higher here than
  in `career_postseason`: Horace Grant, Dennis Rodman, and Byron Scott enter
  its top 20 from 1984.
- A player traded during the season gets a share of each team's playoff
  run, since the lake cannot order a season's stints.
- Before 1958 nothing counts, so Bill Russell's 1957 title and George
  Mikan's are missing. ABA playoffs never count.
- In the six- and eight-team fields of the 1960s the weakest playoff team
  was relatively strong, so a win then earns a little less.
- A season counts once its win shares reach `nba.player_seasons`. Until
  then its runs are missing.

## Use

```
nba sql "from career_postseason_basic() limit 20"
nba sql "from postseason_basic_season_credit() where season = 1965 order by credit desc"
nba sql "from postseason_team_credit(rounds := 'from_final', first_season := 1958) where season = 1965"
```

## Versions

- 1, 2026-10-24: the definition above. From 1984 its team credit equals
  `career_postseason` v1's on every game.
