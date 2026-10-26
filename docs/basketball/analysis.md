# Principles of basketball analysis

How to turn the lake's numbers into claims a front office analyst would
sign. Read [README.md](README.md) first. Formulas are in
[stats.md](stats.md).

## Normalize before comparing

- **Per possession over per game.** A team that plays 104 possessions a
  night inflates every counting stat of its players next to a team that
  plays 94. Per 100 possessions removes pace. Per 36 minutes removes minutes
  but not pace. Per game removes neither and suits only questions about
  what a fan saw.
- **Possessions are estimated before play-by-play.** The box-score estimate
  is FGA - ORB + TOV + 0.44 x FTA, averaged with the opponent's. Offensive
  rebounds were not recorded before 1973-74, team turnovers before 1968-69,
  or player turnovers before 1977-78, so pace and ratings before then are
  estimates of an estimate.
- **Relative to the league.** Express efficiency against the league that
  season: TS% minus league TS%, or a ratio. A 55 percent true shooting
  season was above average in 2002 and well below in 2026.
- **Qualify on volume.** Set a minimum in minutes, games, or attempts that
  fits the question, and say what it is. The `leaders` macro defaults to 58
  games, the NBA's 70 percent of a schedule. Since 2023-24 the league
  requires 65 games for most awards.
- **Season type apart.** Regular season, playoffs, play-in, and the NBA Cup
  final are different populations. Playoff numbers come against better
  opponents, with tighter rotations, slower pace, and defenses that plan for
  one player.

## Evaluating teams

- **Net rating and margin first.** Point differential per game or per 100
  possessions predicts future results better than record. Simple Rating
  System (SRS) adjusts margin for schedule.
- **Expected wins.** Basketball-Reference's Pythagorean win fraction is
  PF^14 / (PF^14 + PA^14), with season points for and against. Daryl Morey's version uses 13.91 and
  John Hollinger's 16.5. Over 82 games a point of margin is worth about 2.6
  wins (lake). The gap between actual and expected wins is mostly close-game
  luck and regresses the next season.
- **Strip garbage time.** Blowout minutes against bench units distort
  ratings and lineup data. Cleaning the Glass's definition: fourth quarter,
  a margin of 25 or more with 12 to 9 minutes left, 20 or more with 9 to 6
  left, or 10 or more under 6 minutes, and two or fewer starters on the
  floor between both teams.
- **Who played.** A team's season is many teams: healthy, missing its star,
  after a trade. Split by roster state with `nba.game_inactives` before
  judging a team or a coach.
- **Schedule effects.** Rest, back-to-backs, travel, and home court are in
  `nba.team_games`. Strength of schedule matters most early in a season and
  in short samples.
- **The four factors explain why.** Effective FG%, turnover rate, offensive
  rebound rate, and free throw rate, for offense and defense. Oliver
  weighted them roughly 40, 25, 20, and 15 percent. The weights shift by era
  and are a guide to where to look, not a formula.

## Evaluating players

Work in this order, and do not skip to an impact metric.

1. **Role and opportunity.** Minutes, usage, and what he is asked to do.
   Starter or bench, creator or finisher, which lineups.
2. **Scoring.** True shooting relative to the league, at his usage, with
   the shot profile behind it: rim, midrange, three, free throws,
   assisted or self-created, catch-and-shoot or pull-up.
3. **Creation for others.** Assist rate, potential and secondary assists,
   drives, and turnovers. A creator's turnovers are a cost of his creation,
   judge them per touch or against assists.
4. **Defense.** Matchups, rim protection, scheme fit, and the plus-minus
   based metrics. State the uncertainty.
5. **Impact.** Several metric families side by side. Explain where they
   disagree in terms of the steps above.
6. **Availability.** Games played is value. A great player who plays 45
   games gave his team 45 games.

### Concepts that come up

- **Scalability and portability.** Whether a player's value holds next to
  other good players. Shooters, cutters, and switchable defenders scale. A
  ball-dominant scorer's value can shrink beside another one.
- **Replacement level.** The value a team could get for free, from the end
  of the bench or the open market. VORP sets it at -2.0 BPM. Value above
  replacement credits playing time, value above average does not.
- **Peak and longevity.** Career totals reward longevity. Best three or five
  seasons measure peak. Say which one the question asks for.
- **Playoff resilience.** Some scorers' efficiency falls in the playoffs
  because defenses can game plan and hunt. The samples are small, and a few
  series against elite defenses carry heavy weight.
- **Era strength.** League quality changes with expansion, integration, the
  ABA split, and the influx of international players. The lake's `era_wins`
  metric translates seasons into the 2025-26 league.

## Noise and sample size

- **Every rate is skill plus luck.** The fewer the trials the more luck.
  Three-point percentage takes many hundreds of attempts to say much about a
  shooter. Free throw percentage settles faster and predicts future
  three-point shooting better than a small three-point sample does.
- **Shrink toward a prior.** For a rate, (makes + k x prior) / (attempts +
  k), with the prior the league or position average and k the attempts at
  which the stat is half signal. Estimate k from the lake with a split-half
  correlation (odd games against even games) instead of quoting a number.
- **Opponent three-point percentage is mostly noise.** Defenses control how
  many threes they allow and how open they are much more than whether they
  go in. Judge three-point defense by attempts allowed and contest rate.
- **Clutch performance mostly regresses.** Late-and-close samples are a
  few hundred possessions a season. Treat clutch splits as anecdotes unless
  they persist over many seasons.
- **The hot hand is small.** Gilovich, Vallone, and Tversky (1985) found no
  hot hand. Miller and Sanjurjo (2018) showed their method was biased
  against finding one, and corrected studies find a small effect. Players
  who feel hot also take harder shots, which hides it in raw percentages.
- **On/off and lineups are noisy.** A player's off-court minutes may be a
  few hundred possessions against bench units. Five-man lineups rarely
  reach a sample that means much. Use the `lineups` macro's minimum and
  report possessions.
- **Single-season RAPM is noisy.** Prefer multi-season or prior-informed
  versions (`adj_rapm`).

## Causal traps

- **Score effects.** Teams that lead slow down, run clock, and rest
  starters. Teams that trail shoot more threes and foul. Any stat split by
  game state carries this.
- **Selection.** Coaches give minutes to players who are playing well and
  close games with their best lineups. Players rest when the game is
  decided. Usage and minutes are outcomes, not independent inputs.
- **Collinearity.** Teammates who share most of their minutes cannot be
  separated by plus-minus. Starters' on/off compares them with bench units.
- **Survivorship.** Long careers belong to players who were good. Aging
  curves built from survivors look flatter than the truth.
- **Regression to the mean.** An extreme season is partly luck and the next
  one is usually closer to average. That is not decline or a coaching
  effect.
- **Composition across eras.** A league-wide trend can come from who plays,
  not from any player changing. Check within players before claiming a
  change in skill.

## Shot quality and shot making

Separate the shot from the shooter. Shot quality is what a league-average
shooter would score on the same shot: location, defender distance,
catch-and-shoot or pull-up, shot clock. Shot making is the residual. The
lake has location in `nba.shots` from 1996-97 and closest defender bands
(0-2, 2-4, 4-6, 6+ feet) in `nba.player_season_closest_defender` from
2013-14. A player with a great percentage on wide-open catch-and-shoot
threes is benefiting from the offense around him as much as from his touch.

## Data artifacts that look like basketball

- **Scorekeeper bias.** Assists, blocks, and steals are judgment calls by
  each arena's scorers, and some arenas credit them more generously.
  Compare home and road splits before trusting a small difference.
- **Play type is the last action.** Synergy credits a possession to the
  action that produced the shot, turnover, or foul. A pick and roll that
  ends in a kick-out three counts as a spot-up for the shooter, so pick and
  roll ball-handler points per possession understates the action's value.
- **Tracking starts in 2013-14.** Drives, touches, contested shots, and
  defender distances do not exist before then. Hustle stats and play types
  start in 2015-16, matchups in 2017-18.
- **Pre-1973-74 box scores lack** steals, blocks, offensive rebounds, and
  player turnovers, which start in 1977-78. Never rank those players on them, and treat their advanced
  stats as estimates.
- **Rebound totals track misses.** The 1960s had more rebounds because
  teams missed more shots and played faster. Compare rebound rate, which
  needs offensive and defensive rebounds and so exists only from 1973-74.

## The shape of a good analysis

1. State the basketball question and the mechanism you expect.
2. Pick the grain (possession, game, season, career) and the population.
3. Set the baseline: the league, the position, replacement, or the player's
   own history.
4. Compute with sample sizes beside every rate.
5. Check the result against cases a fan knows, and against a second method.
6. Explain the result in basketball terms, then say what the data cannot
   see.
