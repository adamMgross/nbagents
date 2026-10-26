# Basketball for analysts

Read this page before any analysis of the lake. It is the floor of
basketball understanding an analysis needs: what the game is made of, what
the numbers mean, and where they mislead. The topic pages go deeper. Read
the ones the question touches before writing SQL.

| Page | Read when the question involves |
|---|---|
| [analysis.md](analysis.md) | any ranking, comparison, or claim about value. Always for a report or a metric |
| [stats.md](stats.md) | a named stat or impact metric: its formula, scale, and blind spots |
| [offense.md](offense.md) | play types, actions, systems, shot selection, a player's offensive role |
| [defense.md](defense.md) | defensive value, pick and roll coverage, zone, rim protection, matchups |
| [history.md](history.md) | more than one era, a rule change, a record, or anything before 2000 |

Numbers on these pages marked "lake" were computed from the lake on
2026-10-25. Recompute them when an analysis leans on one.

## What the game is made of

- **The possession is the unit.** A possession ends on a made field goal or
  last free throw, a defensive rebound, or a turnover. An offensive rebound
  extends it. Both teams get nearly the same number of possessions in a
  game, so games are won by scoring more per possession. Pace, possessions
  per 48 minutes, is a style choice that inflates or deflates every counting
  stat without changing who is better.
- **Points per possession is the score that matters.** Offensive rating is
  points per 100 possessions, net rating is offensive minus defensive. The
  league averaged 115.8 in 2025-26 (lake). A season net rating near +11 is
  historic: only eight NBA teams have finished with a margin above +11 per
  game, among them the 1995-96 Bulls and the 2024-25 Thunder (lake).
- **Shot value is geometry.** Points per shot in the 2025-26 regular season
  (lake): 1.37 at the rim (0-3 ft), 1.08 on threes, 0.90 from 4-13 ft, 0.83
  on long twos (14 ft and out). A 36 percent three is worth a 54 percent
  two. Offenses hunt the rim, the three, and the free throw line. Defenses
  try to force long twos and contested floaters.
- **Offense creates an advantage, then passes it on.** A possession starts
  five on five and balanced. An action (a ball screen, a drive, a post
  touch, an off-ball screen, a mismatch) bends the defense until someone is
  open, and good offense keeps the ball moving until the advantage becomes a
  good shot. The scorer is often not the creator. Points credit the
  finisher, assists credit the last pass, and nothing in the box credits the
  screen, the drive that drew help, or the shooter whose gravity kept a
  defender out of the paint.
- **Defense shrinks space and time.** Five defenders guard one ball. The
  other four sit between their man and the basket, help on drives, and
  recover. Defense is a system and its weakest defender gets hunted. The box
  score sees almost none of this: steals, blocks, and defensive rebounds are
  a small and biased sample of defensive work.
- **The pick and roll is the center of the modern half court.** Most
  half-court possessions involve a ball screen, and the coverage a team
  chooses against it (drop, switch, hedge, blitz, ice) defines its defense.
- **Spacing is a shared resource.** A shooter pulls his defender away from
  the paint. A non-shooter lets his defender help freely, which shrinks the
  floor for all four teammates. This is why shooting bigs became valuable
  and why a non-shooter's teammates can look worse with him on the floor.
- **Possessions are won and lost in four places.** Shooting efficiency,
  turnovers, offensive rebounds, and free throws, Dean Oliver's four
  factors, in roughly that order of importance.
- **Positions are roles now.** Guard, forward, and center describe size more
  than job. Analyze by role: primary creator, secondary creator, spot-up
  shooter, connector, roll man, stretch big, rim protector, point-of-attack
  defender, wing stopper.
- **Usage and efficiency trade off.** A player's efficiency usually falls as
  he takes a larger share of his team's possessions, because the extra shots
  are harder. Someone must take the late-clock shots. A high-usage scorer at
  league-average efficiency can be worth more than an efficient low-usage
  role player. Compare efficiency at similar usage.

## What the numbers say and do not say

- **Rate, then volume, then context.** Per-game totals mix skill, minutes,
  and pace. Per 100 possessions is the fair rate. Then ask how much volume
  (minutes, usage, attempts) the rate came on, then in what context (era,
  team, role, health, opponent).
- **The league changed underneath the numbers.** League true shooting went
  from 41 percent in 1949-50 to 58 percent in 2025-26. Team three-point
  attempts went from 2.8 a game in 1979-80 to 37. Pace went from about 126
  in 1959-60 to 89 in 1998-99 and back to 99 (lake). Compare a player to
  his own league and season. See [history.md](history.md).
- **Small samples lie.** Three-point percentage wanders widely over a few
  hundred attempts. On/off, clutch, lineup, and playoff splits are noisy.
  Opponent three-point percentage is mostly luck. One game proves nothing.
  State the sample beside every rate and shrink small samples toward a
  sensible prior.
- **The box score barely sees defense.** Steals and blocks reward gambling
  and size. Use plus-minus based impact metrics, tracking data, and
  matchups, and say how uncertain a defensive claim is.
- **Impact metrics are estimates with different blind spots.** Box-based
  metrics (PER, Win Shares, BPM) see only the box. Plus-minus based ones
  (RAPM) see everything that changes the score but are noisy and confuse
  teammates who share minutes. Hybrids (RPM, EPM, LEBRON, RAPTOR, DARKO)
  blend the two. Agreement across families is evidence. Disagreement tells
  you what kind of player it is.
- **Margin predicts better than record.** One point of average margin is
  worth about 2.6 wins over 82 games (lake, 1989-90 on, r 0.97). A record
  built on close wins tends to regress.
- **Home court is worth less than it was.** Home teams won about 65 percent
  of regular season games in the 1980s and 55 percent in the 2020s (lake).
- **The box does not hold the context.** Injuries, rest and back-to-backs,
  garbage time, tanking, coaching scheme, lineup partners, and playoff
  adjustments all move numbers. Check who was on the floor.

## Before reporting a number

- **Smell test.** Look at who leads the list. A knowledgeable fan should
  recognize the names or the reason they are there. A bench player atop an
  efficiency list means the minimum filter is too low.
- **Denominator.** Per game, per minute, per possession, or per attempt, and
  the minimum that qualifies. Match it to the question.
- **Like with like.** Same league, era, season type, and role. The ABA and
  the early BAA are their own leagues.
- **Signal over noise.** Is the effect larger than its sampling noise? Would
  it survive a second season of data?
- **Mechanism.** Name the basketball reason behind the finding: a scheme, a
  role, spacing, a matchup, a rule change. A finding no coach could explain
  is usually noise or a data artifact.
