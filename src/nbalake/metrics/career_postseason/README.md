---
name: career_postseason
version: 2
summary: Career postseason achievement from 1984, as playoff wins above what the season's weakest playoff team would have won against the same opponents, weighted by round and split by each player's share, which from 1994 reflects how he played that postseason.
---

# Career postseason achievement

## Question

Whose playoff careers achieved the most? The metric rewards winning, more so
against strong opponents and deeper in the bracket, and credits each player
by how much he drove his team. It does not punish a team for being the
favorite, and losing to a great team costs little.

## Definition

```
playoff game, per team          per player in that game        sums
---------------------------     ---------------------------    ----------------
won - baseline_win_prob    ->   x 5 x share               ->   run = season sum
x round_weight                  = credit                       career = run sum
= team_credit
```

For every NBA playoff game from 1983-84 (season 1984) on, for each team:

1. `baseline_win_prob` is the chance a baseline team wins this game, against
   this opponent, at this venue: `elo_game_prob(baseline_elo, opponent_elo,
   venue_edge)`.
   - `baseline_elo` is the lowest Elo any playoff team carried into its first
     playoff game that season (`baseline := 'weakest'`).
   - Elo is the lake's fitted Elo where it exists (2014-15 on) and
     FiveThirtyEight's before.
   - `venue_edge` is the season's home edge, fitted from 2014-15 and 100
     before. It is 0 at a neutral site and negative on the road.
2. `team_credit` is `(won - baseline_win_prob) * round_weight`, where
   `round_weight` is the round from `nba.playoff_series`, 1 for the first round
   to 4 for the Finals (`rounds := 'linear'`).
3. `share` splits the team's credit among its players.
   - From 1993-94, a player's weight is his seconds in that game times
     `max(regular-season BPM + playoff_bpm_adjustment + 2, 0)`, with a
     missing BPM counted as -2. His share is his weight over the team's
     total in that game. A player who sat out a game gets nothing from it.
   - `playoff_bpm_adjustment` says how much better or worse he produced that
     postseason than in the regular season with the same team, in BPM
     points:
     `0.6 * (gain - season mean gain) * minutes / (minutes + 750)`.
     - `gain` is his Game Score per 36 minutes over the whole postseason
       minus his regular-season rate, from `nba.player_box`.
     - The season mean gain, weighted by playoff minutes, is subtracted
       because tougher playoff defenses lower almost everyone's rate, about
       one point per 36 minutes. Only playing better than that counts.
     - 0.6 converts Game Score per 36 into BPM, the slope of BPM on Game
       Score per 36 over regular seasons from 1997 with 500 minutes or more.
     - `minutes / (minutes + 750)` shrinks the gain by playoff minutes. At
       750 minutes half of it counts.
     - A player with under 500 regular-season minutes for the team gets no
       adjustment.
   - Before 1993-94 no playoff box scores exist, so the weight is
     regular-season minutes times `max(BPM + 2, 0)`, over the team's season
     roster, applied to every playoff game.
4. `credit` is `5 * team_credit * share`. The 5 puts credit on the scale of
   one of five players: a player with an even fifth earns the team's whole
   credit.

A run is a player's credit summed over his team's games that postseason, and
a career is the sum of runs.

## Why these choices

The owner set three cases any definition had to get right, and a fourth for
version 2. Version 2 passes all four.

- Kobe Bryant 2008 lost the Finals to a great Celtics team. That run keeps
  84% of his 2001 title run's credit, because losing to a great team costs
  little.
- Magic Johnson 1989 was hurt for most of the Finals. The run still ranks
  79th of 9,066 player runs, below his 1987 title (28th).
- LeBron James 2016 beat the 73-9 Warriors. It is the 3rd-best run, behind
  Michael Jordan 1993 and Nikola Jokić 2023.
- Kawhi Leonard 2019 outplayed his regular season. Version 1, on
  regular-season BPM alone, ranked the run 36th. Version 2 ranks it 26th,
  and his career 17th instead of 18th.

The playoff adjustment is modest by design. Splitting each run's games in
half, the two halves' gains correlate at 0.22 over 1,841 runs, so a run of
the average 438 minutes is about 37% signal. That reliability sets the 750
minutes, and it keeps every adjustment between -2.1 and +2.0 BPM.

Rejected alternatives:

- How close the team got to a title, from series odds. It punishes a team
  for meeting a great opponent, which fails Kobe 2008.
- A blend of series wins added and opponent difficulty. Losing the Finals is
  worth about half a title even to a great opponent or when hurt.
- The average playoff team as the baseline (`baseline := 'average'`). Losses
  cost much more, and Kobe 2008 drops to half a title.
- Flat round weights (`rounds := 'flat'`). A Finals loss scores about the
  same as a title, so winning stops mattering.
- Shares from the player's own playoff Game Score in place of BPM. They exist
  only from 1993-94, and the regular-season split before concentrates credit
  on stars, so the two eras disagree and the 1980s dominate.
- A playoff adjustment from play-by-play, the team's margin with the player
  on court against its margin overall, from `nba.possessions`. Stars play
  more of the playoffs, so their on-court margin drifts toward the team's
  and the adjustment punishes them: LeBron 2016 fell as far as 19th and
  Stephen Curry 2022 to 99th.
- On/off from play-by-play, the margin on court against off court. Too
  noisy over one postseason even shrunk: Jokić 2023 fell from 2nd as far
  as 1,243rd and Kobe 2008 to 34% of his 2001 run.
- The Game Score gain without subtracting the season mean. The across-the-
  board playoff drop then lowers every player's BPM alike, which shifts
  share toward stars regardless of how anyone played.

## Limits

- It starts in 1984, the first 16-team bracket, since the round weights
  assume four rounds. Earlier titles, like Magic Johnson's 1980 and 1982 and
  every Bill Russell title, do not count.
- How a player played in the playoffs enters from 1994 only through his box
  score. Defense that leaves no box trace goes unseen, and before 1994
  quality is regular-season BPM alone.
- Before 1993-94 shares come from the regular season. An injured player still
  gets his share of the games he missed, and a player traded away during the
  season gets a share of his old team's playoff games, since the lake cannot
  order a season's stints.
- Credit is a scaled score, not wins. Compare it across players and runs,
  not with win totals.
- Playoffs in progress count as they are played.

## Use

```
nba sql "from career_postseason() limit 20"
nba sql "from postseason_season_credit() where player_id = 2544 order by season"
nba sql "from postseason_game_credit() where season = 2016 and player_id = 2544"
nba sql "from postseason_team_credit() where season = 2016 and round = 4"
nba sql "from career_postseason(baseline := 'average', rounds := 'flat') limit 20"
nba sql "from career_postseason(playoff_adjustment := false) limit 20"
```

`postseason_team_credit` holds steps 1 and 2, one row per team per game.
`postseason_game_credit` adds the share and is the place to ask why a run
scored what it did: each row carries the Elo, the baseline's chance, the
round weight, the regular-season BPM, the playoff adjustment, and the share.
`playoff_adjustment := false` gives version 1's numbers.

## Versions

- 1, 2026-10-24: shares from regular-season BPM alone. It reproduces the
  prototype that settled it to within 1e-6 on all 9,066 player runs from
  1984 to 2026.
- 2, 2026-10-24: the playoff Game Score adjustment from 1994. Runs before
  1994 are unchanged. The career top 20 holds the same players, with Draymond
  Green and Kawhi Leonard each up one place. LeBron James 469.1, Michael
  Jordan 389.6.
