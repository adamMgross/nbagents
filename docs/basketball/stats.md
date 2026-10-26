# Stats and metrics

What each common number measures, how it is built, its scale, and what it
misses. Where the lake holds a stat, the table is named. Lake metrics of
the repo's own (`era_wins`, `career_postseason`) are documented by `nba
metrics`.

## Shooting and efficiency

| Stat | Definition | Note |
|---|---|---|
| eFG% | (FGM + 0.5 x 3PM) / FGA | Field goals only, a three counts 1.5 makes |
| TS% | PTS / (2 x (FGA + 0.44 x FTA)) | The scoring efficiency summary. 0.44 is the share of free throws that use a possession |
| 3PAr | 3PA / FGA | Shot profile, not skill |
| FTr | FTA / FGA | Basketball-Reference's free throw rate |
| FT factor | FTM / FGA | Oliver's four-factor version, rewards making them |
| Points per shot | PTS from FG / FGA | By zone it is the shot value map |
| PPP | Points per possession | Synergy play types use it per play |

## Possessions and ratings

| Stat | Definition | Note |
|---|---|---|
| Possessions | FGA - ORB + TOV + 0.44 x FTA | Average with the opponent. Estimated before 1973-74 |
| Pace | Possessions per 48 minutes | Style, not quality |
| ORtg, DRtg | Points scored, allowed per 100 possessions | Team versions are exact. Oliver's player versions are estimates, the defensive one weak |
| Net rating | ORtg - DRtg | Team quality per 100 possessions |
| MOV | Points per game minus allowed | Scales with pace |
| SRS | MOV adjusted for opponents' strength | Basketball-Reference, in `bref.team_summaries` |

## Rates of a player's share

All are measured while the player is on the floor.

| Stat | Meaning |
|---|---|
| USG% | Share of team plays (FGA + 0.44 x FTA + TOV) he used |
| AST% | Share of teammates' field goals he assisted |
| TOV% | Turnovers per play used: TOV / (FGA + 0.44 x FTA + TOV) |
| ORB%, DRB%, TRB% | Share of available rebounds he grabbed |
| STL% | Steals per opponent possession |
| BLK% | Blocks per opponent two-point attempt |

## Box-score composites

- **PER** (John Hollinger, early 2000s). Per-minute, pace-adjusted linear
  weights of the box score, scaled so the league average is 15. Rewards
  shot volume even at mediocre efficiency and rebounds heavily. Barely
  sees defense. 20 is a good starter, 25 an All-NBA level, 30 historic.
- **Win Shares** (Justin Kubatko, Basketball-Reference, built on Oliver's
  points produced). Offensive and defensive win shares sum to team wins.
  WS/48 averages about 0.100. Defensive win shares are mostly team defense
  split by minutes and rebounds, so they flatter players on good defenses.
- **BPM** (Daniel Myers 2014, BPM 2.0 in 2020). A regression of box stats
  and position onto long-term RAPM. Points per 100 possessions above an
  average player. Basketball-Reference's scale: +10 an all-time season, +8
  MVP, +6 All-NBA, +4 All-Star consideration, +2 a good starter, 0 a
  decent starter, -2 replacement.
  Among 2025-26 players with 1,500 minutes the median was +0.7, the 90th
  percentile +4.2, the 99th +11.2 (lake). Basketball-Reference computes it
  from 1973-74.
- **VORP**. (BPM + 2.0) x share of team minutes x team games / 82. BPM
  turned into a counting stat above replacement.
- **Game Score** (Hollinger). A quick one-game linear weights line, roughly
  on the scale of points.

## Plus-minus family

- **Plus-minus and on/off.** Team margin with a player on the floor, and
  the difference from his minutes off it. Sees everything that changes the
  score, including defense and spacing, and confuses a player with his
  teammates and opponents. Game plus-minus starts in 1996-97 in the lake.
- **APM.** Wayne Winston and Jeff Sagarin's WINVAL for the Mavericks in the
  early 2000s, made public by Dan Rosenbaum in 2004: a regression on every
  stint of who was on the floor, to separate teammates.
- **RAPM.** Joe Sill's 2010 ridge-regularized APM, which shrinks every
  player toward zero to tame the noise. Multi-season RAPM is the closest
  thing to ground truth for impact and is the target many metrics fit.
  `nba.player_impact.rapm` is single season, `adj_rapm` uses a box prior.
- **Hybrids.** ESPN's RPM (2014), FiveThirtyEight's RAPTOR (2019 to 2023,
  in `nba.raptor` through 2021-22), EPM (Dunks and Threes), LEBRON (BBall
  Index), and DARKO (Kostya Medvedovsky, a projection). Each blends a box
  or tracking prior with plus-minus. They agree more than they differ.
  When they differ, look at the box against the on-court results.
- **WAR.** Impact in points per 100 turned into wins above replacement with
  minutes and points per win. `nba.player_impact.war` and the lake's
  `era_wins` are two versions.

## Team and game models

- **Pythagorean wins.** Exponent 14 on Basketball-Reference, 13.91 for
  Morey, 16.5 for Hollinger.
- **Elo.** FiveThirtyEight's ratings, 1500 average, a fixed home edge, and
  carryover toward the mean between seasons. The lake continues them from
  2015-16, with a fitted home edge beside the fixed one (`nba.team_games`).
- **Betting lines.** The closing spread is the best single public forecast
  of a game. `nba.game_lines` from 2006-07.

## Tracking era

From 2013-14 unless noted, in `nba.player_season_tracking` and neighbors.

- **Shooting context.** Catch-and-shoot against pull-up, and the closest
  defender at the shot: very tight 0-2 ft, tight 2-4, open 4-6, wide open
  6 or more.
- **Creation.** Drives, touches (elbow, post, paint), time of possession,
  potential assists (passes that would be assists if made), secondary
  assists.
- **Defense.** Defended field goal percentage at the rim and overall,
  contested shots, deflections, charges drawn (hustle from 2015-16), and
  matchups per offensive and defensive player pair from 2017-18
  (`nba.matchups_season`), which apportion partial possessions.
- **Effort and size.** Speed and distance, box outs, screen assists
  (screens that led directly to a made shot), loose balls recovered.
- **Play types.** Synergy's video-logged categories from 2015-16
  (`nba.player_season_play_types`), described in
  [offense.md](offense.md).

## Scales at a glance

2025-26 regular season, players with 1,500 minutes unless noted (lake).

| Stat | Average or median | Elite |
|---|---|---|
| TS% | 58.5 median, league 58.1 | 63.7 at the 90th percentile |
| USG% | 20.2 median | 31.6 at the 95th percentile |
| BPM | +0.7 median | +4.2 90th, +11.2 99th |
| WS/48 | 0.112 median | above 0.200 is a star |
| PER | 15 league by construction | 25 and up |
| Team net rating | 0 | +10 is a champion's profile |
