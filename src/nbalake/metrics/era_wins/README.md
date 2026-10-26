---
name: era_wins
version: 1
summary: Wins above replacement per player season from 1974, in its own league and translated into the 2025-26 league by league strength, the free throw whistle, and wins per point, so seasons compare across eras.
---

# Era wins

## Question

How much did a player add to winning in a season, measured against his
contemporaries, and what would that season be worth in today's league? Raw
totals mix pace, minutes, the rules defenders played under, and how deep the
league's talent was. A 35 point season in 1987 and one in 2006 are not the
same feat, and a triple double per game in 1962 is mostly pace and minutes.
The metric must reward impact relative to peers and must not punish a player
for the rules, scorekeeping, or talent pool of his era.

## Definition

```
BPM (points per 100 above league average, already relative to peers)
  |
  +--> wins          = (BPM + 2) x minute share x season wins per point x games / 82
  |
  +--> neutral BPM   = BPM + whistle_adj + strength
         |
         +--> neutral_wins = (neutral BPM + 2) x minute share x 2025-26 wins per point
```

1. `bpm` is Basketball-Reference BPM, the one impact rating that spans
   1974-2026 under one method. Replacement is -2, as in VORP.
2. `minute_share` is minutes over the average team's minutes / 5.
3. `wins_per_point()` is 82 times the slope of win percentage on net rating,
   pooled within seasons over five seasons. It falls from about 2.8 in the
   late 1970s to 2.2 now: as three point shooting makes single games more
   random, a point of margin buys fewer wins.
4. `whistle_trips()` and `free_throw_environment()` measure the whistle from
   1997 play-by-play in three channels: two-shot trips after a shooting foul
   per two-point attempt within 10 feet, and-ones per make within 10 feet, and
   three-shot trips per three-point attempt. Bonus free throws are left alone.
   Before 1997 every season takes 1997's rates, and a player's free throws
   split across channels as the league's did in 1997.
5. `whistle_adj` scales the player's free throw points in each channel by the
   2025-26 rate over his season's rate, per 100 possessions, minus the
   season's minute weighted mean, so it moves a player only against his peers.
6. `league_strength()` has two parts. The year to year steps come from every
   player with 800 minutes in back to back seasons: the mean change in BPM,
   minus an age curve, is how much the league around him changed (Berry,
   Reese, and Larkey 1999). That cannot see a steady trend, because a league
   improving every year looks like players aging faster. The trend comes from
   the talent pool: the league fills 10 spots per NBA and ABA team, the
   US-born share of those spots draws on the US population, and `talent_z` is
   the normal quantile of that selection rate. Regressing the steps on the
   change in `talent_z` gives the BPM worth of one standard deviation of the
   bar (8.4) and the drift that the steps alone cannot fix. `strength` is the
   sum of drift minus step, zero at 2025-26.
7. `career_era_wins()` sums seasons and reports the best season and the best
   five. `partial` is true for a career with seasons the metric does not
   count, before 1974 or in the ABA.

## Why these choices

The owner's cases, from the macros on 2026-10-24:

| Season | BPM | wins | rank | neutral_wins | rank |
|---|---|---|---|---|---|
| Jordan 1988 | 13.0 | 32.5 | 1 | 28.2 | 1 |
| Jordan 1987 | 10.8 | 27.2 | 5 | 23.8 | 6 |
| Harden 2019 | 11.0 | 22.8 | 31 | 21.1 | 16 |
| Jokic 2026 | 14.2 | 20.6 | 48 | 20.6 | 20 |
| Westbrook 2017 | 11.1 | 23.3 | 24 | 20.5 | 21 |
| Kobe 2006 | 7.6 | 19.5 | 78 | 15.5 | 101 |

The rule changes show in the whistle rates: two-shot trips per near attempt
rose from 0.194 (1997) and 0.212 (2004) to 0.226 after hand checking was
banned in 2004-05, and three-shot trips per three rose from 0.6 percent to
1.6 percent by 2017 before the 2021-22 crackdown on non-basketball moves cut
them to 0.8. Wade and LeBron in 2009, a generous whistle, lose about 0.65
points per 100. Jordan's seasons move by 0.01, because the 1997 rim whistle
is close to 2025-26's.

League strength: the ABA split 1975 is weakest (-1.16), the merger lifts
the league to -0.63 by 1977, the 1980s are strongest (+0.26 in 1985), the
1989-91 and 1996 expansions thin it, and 2005 sits at -0.81.

Top neutral seasons: Jordan 1988, Jordan 1989, Robinson 1994, LeBron 2009,
Jokic 2024. Top careers: LeBron 349, Jordan 250, Stockton 231, Paul 218,
Malone 209. Jordan's best five seasons (124) lead every career.

Rejected alternatives:

- Scaling BPM by each season's spread, a z-score. 1974-77 BPM uses turnovers
  estimated by regression, which shrinks its spread, so the scaling inflated
  that era (Kareem 1976 from 34th to 5th). A point of margin is the unit of
  winning, so the metric keeps points and leaves dominance to a rank.
- Returning-player bridging alone. It recovers the merger and expansions with
  the right sign but leaves the long run trend to an arbitrary aging anchor.
- Rule effects by role from returning players' BPM. Guards gained 0.39 on
  bigs in 2005 against season noise of 0.3, and 2019 moved the wrong way.
- Free throws per two-point attempt as the whistle. It rose from 0.27 in
  1974 to 0.40 in 1997 because threes replaced twos, not because of the
  whistle, and would have handed 1970s foul drawers 59 percent more free
  throw points.

## Limits

- BPM is a box score estimate. It underrates some players, Kobe 2006 among
  them, and plus-minus data exists only from 1997.
- The whistle adjustment covers the free throw channel only. Rules that
  changed how efficiently guards score from the field, beyond free throws,
  stay in context.
- Before 1997 the whistle is assumed equal to 1997's.
- The talent pool assumes constant US basketball talent per capita and ten
  spots per team. Birthplaces come from Wikidata and population from the
  Census Bureau through FRED.
- Every fit uses every season, so a new season can move older numbers
  slightly. Quote numbers with the version.
- Neutral values are NULL when `reference_season` has no data.

## Use

```sql
from wins_per_point() where season >= 2015
from free_throw_environment() where season >= 2015
from league_strength() order by season
from whistle_trips() where season = 2019 order by three_trips desc limit 10
from era_wins_season() where season = 1988 order by neutral_wins desc limit 10
from career_era_wins() limit 20
```

## Versions

- 1, 2026-10-24: BPM wins in context and translated into 2025-26 by league
  strength, the whistle, and wins per point. The SQL league strength matches
  the iterated prototype within 0.043 BPM on all 52 seasons (mean 0.018).
