---
name: quality_wins
version: 1
summary: Regular-season wins weighted by how hard each one was, against the opponent's strength at the time and the venue, for every team from 1947 and split among the players who played each game.
---

# Quality wins

## Question

Whose regular-season wins were worth the most? A win over a strong team on
the road should count for more than a win over a weak team at home, so a
record built on beating bad teams counts for less than the same record built
on beating good ones. A player is credited for the wins he played in and is
never penalized for a game he missed, injured or resting: that game's credit
goes to the teammates who won it. A loss costs nothing.

It sits beside win shares in the box-score family (`docs/basketball/stats.md`)
and beside `career_postseason` in spirit, credit for winning against strong
opponents. It addresses the blind spot of a plain record, which counts every
win the same.

## Definition

```
regular-season game, per team             per player in that game      sums
---------------------------------------   --------------------------   ---------------
if won: 1 - average_win_prob          ->  x share                  ->  team season
        / season mean over all wins        = credit                     player season
      = difficulty = credit                                             career
if lost: 0
```

For every NBA and BAA regular-season game from 1946-47 (season 1947) on, for
each team:

1. `average_elo` is the season's mean pre-game Elo over every team-game.
   Expansion pulls the league mean well below 1500 in some seasons, so the
   average team is the season's own.
2. `average_win_prob` is the chance a team of `average_elo` wins this game,
   against this opponent, at this venue:
   `elo_game_prob(average_elo, opponent_elo, venue_edge)`. Elo is the lake's
   fitted Elo where it exists (2014-15 on) and FiveThirtyEight's before.
   `venue_edge` is the fitted home edge from 2014-15 and 100 before, 0 at a
   neutral site and negative on the road.
3. `difficulty` is `1 - average_win_prob`, the chance an average team would
   have lost the game, divided by its mean over every win that season. The
   season's average win counts 1. A game with no Elo for either team counts
   1.
4. `credit` is `difficulty` for a win and 0 for a loss. A season's quality
   wins over every team add up to its wins, so a team's `above_record`,
   quality wins minus wins, says how much harder its wins were than the
   league's.
5. `share` splits a team's game credit among its players.
   - From 1993-94, a player's weight is his seconds in that game times his
     regular-season win shares per minute for that team, floored at 0. Only
     players who played the game share it.
   - Before 1993-94 no box scores exist, so the weight is his season's win
     shares for that team, floored at 0, applied to every game.
   - A game whose weights are all 0 splits by seconds, or evenly before
     1993-94.
   - `shares := 'minutes'` weighs by seconds alone.

Win shares are built to add up to a team's wins, which is this metric's unit,
so they split each game's credit in the same proportions a season's wins are
split.

## Why these choices

The cases version 1 had to get right:

- A team that beats up on bad teams. The 2013-14 Indiana Pacers won 56
  games, 4th in the league, and fall to 9th with 51.3 quality wins, the
  largest shortfall of any team with 55 or more wins (-4.7).
- The best seasons stay on top. The 2015-16 Golden State Warriors, 73-9, lead
  every season with 81.7 quality wins, ahead of the 1995-96 Chicago Bulls at
  79.9.
- A missed game costs nothing. Kawhi Leonard played 60 games for the 2018-19
  Toronto Raptors, who went 41-19 in them, and earns 9.14 quality wins from
  those games. The 22 games he sat, 17 of them won, go to the teammates who
  played them.
- Players are credited in proportion to their teams' wins. Michael Jordan's
  1987-88, his best season, earns 22.6 of the Bulls' 50 wins, close to his
  21.2 win shares.

Rejected alternatives:

- Wins minus what an average team would have won against the same schedule,
  as `career_postseason` does with its baseline. Its season total is the
  record minus a constant of the schedule, so two teams with the same record
  and schedule score the same whoever they beat, which is the distinction
  this metric exists to draw.
- Shares by minutes times `max(BPM + 2, 0)`, as `career_postseason` splits.
  That weight treats every win as value above a replacement player, so a
  team's wins go to its stars: Jordan's 1987-88 took 42.7 of the Bulls' 50
  wins, and in a season-level check the 99th percentile player season took
  54% of his team's, against 33% by win shares.
- Shares by minutes alone. It credits presence, so career totals become
  minutes played: Robert Parish and John Havlicek reach the top 11. It stays
  as `shares := 'minutes'`.
- Difficulty without the season scaling. The average win is then worth 0.88,
  and the scale drifts with each season's spread of team strength.

## Limits

- Elo is a running estimate. Early in a season it leans on the previous one,
  and it moves with the results this metric counts.
- Shares come from win shares, a box-score stat. Defense enters mostly as
  team defense split by minutes, so a great individual defender gets little
  more than his teammates for it.
- Before 1993-94 a player's share applies to every game his team played that
  season, including games he missed, and a traded player gets a share of each
  of his teams' whole seasons, since the lake cannot order a season's stints.
- 26 team games from 1993-94 to 2012-13 have no player box, so their 5.3
  quality wins go to no player. Team totals include them.
- Totals depend on the schedule: lockout and pandemic seasons hold fewer
  games, and the current season counts as it is played.
- ABA seasons are left out.

## Use

```
nba sql "from quality_win_team_season() where season = 2014 order by rank"
nba sql "from quality_win_team_game() where season = 2016 and team_id = 1610612744 order by credit desc limit 5"
nba sql "from career_quality_wins() limit 20"
nba sql "from quality_win_season() where player_id = 202695 order by season"
nba sql "from quality_win_game() where season = 2019 and player_id = 202695 order by credit desc limit 5"
nba sql "from career_quality_wins(shares := 'minutes') limit 20"
```

`quality_win_team_game` holds steps 1 to 4, one row per team per game, with
the opponent's Elo, the average team's chance, and the difficulty.
`quality_win_game` adds the share and is the place to ask why a season
scored what it did.

## Versions

- 1, 2026-10-25: the definition above. The team grain reproduces the
  prototype to within 1e-9 on all 137,112 games with Elo, and the player grain
  reproduces an independent prototype of the win share split to within 1e-9
  on all 1,672,718 rows where every weight is not 0. Kareem Abdul-Jabbar
  287.6, LeBron James 281.6.
