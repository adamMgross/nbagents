# Defense

The principles, coverages, and personnel of NBA defense, and how little of
it the data sees. Read [README.md](README.md) first.

## Principles of man-to-man

- **Ball pressure and containment.** The on-ball defender keeps the handler
  in front and out of the middle. Getting beaten forces everyone else to
  help, and the advantage spreads.
- **Help position.** Off-ball defenders sit between their man and the
  basket, closer to the ball the farther their man is from it. One pass
  away they deny or play the gap. Two passes away they sink into the paint
  to help (the pack line idea).
- **The nail.** The middle of the free throw line, where a help defender
  can stunt at a drive and still recover to a shooter.
- **Tag and low man.** The weak side defender nearest the basket bumps the
  roll man or a cutter so the rim is never open.
- **Rotate and recover.** When one defender helps, the next one helps the
  helper, and the last one splits two shooters. X-out rotations sprint the
  farthest defender to the farthest shooter.
- **Closeouts.** Run at the shooter, chop the feet, hands high. Close out
  hard to a great shooter and under control to a driver. A late closeout
  gives up either an open shot or a drive past a defender off balance.
- **Shrink the floor.** Help off non-shooters and stunt at drives so the
  lane looks crowded.
- **Finish with the rebound.** Every defender boxes out. A forced miss is
  wasted without the defensive rebound.
- **Transition defense.** Get back, stop the ball first, protect the rim,
  then match up. Teams that crash the offensive glass give some of this up.

Rules shape what help is allowed. Before 2001-02 illegal defense rules
limited help away from the ball. Since then zones are legal and the
defensive three seconds rule stops a defender standing in the lane for
more than three seconds unless he is guarding someone there.

## Pick and roll coverages

| Coverage | The big | The guard | Gives up |
|---|---|---|---|
| Drop | Sinks into the paint between the free throw line and the rim | Chases over the screen from behind | Pull-up jumpers and floaters. Ruined by elite pull-up shooters |
| At the level, up to touch | Meets the handler at the screen | Fights over | Pocket passes and short rolls |
| Hedge or show | Jumps out to stop the handler, then recovers to the roller | Recovers to the handler | A brief two on one behind the play |
| Blitz or trap | Doubles the handler with the guard | Doubles | A four on three behind the ball after the pass. Used against stars like Stephen Curry |
| Switch | Takes the handler | Takes the screener | Mismatches: a big on a guard, a guard posted by a big |
| Ice, blue, or down | Drops on the side the handler is forced to | Steps above the screen to force the handler to the baseline | Baseline jumpers and a long pocket pass |
| Under | Stays home | Goes under the screen | An open pull-up. Only against poor shooters |

Variations: switch the guards and forwards but keep the center in drop, a
**scram** switch to swap a mismatch back off the ball, a **peel** switch
to cover a beaten defender. A good defense changes coverage by opponent
and by game, and the choice depends on whether its big can move on the
perimeter and whether the handler can shoot off the dribble.

## Off-ball screens and handoffs

Trail (chase over the screen, staying attached to the shooter), top lock
(stand above the screen to deny the curl), shoot the gap (go under on a
non-shooter), switch, and jump the handoff (hit the receiver before the
catch). A flare defeats a trailing defender. A curl punishes a top lock
that is late.

## Zones and presses

- **Zones.** 2-3 (protects the paint, weak in the high post and corners),
  3-2 and 1-2-2 (contest shooters, weak inside), 1-3-1 (traps the wings,
  weak in the corners and on the glass), matchup zone (zone spacing with
  man assignments), box-and-one and triangle-and-two (a zone with one or
  two defenders shadowing stars). Zones are beaten by flashing to the
  middle, short corner, skip passes, and offensive rebounds, since nobody
  owns a box out.
- **Zones in the NBA.** Legal only since 2001-02, and rarely a base defense
  because shooters punish them and the defensive three seconds rule keeps
  the paint from being packed. Coaches use them for a few possessions to
  change rhythm. The 2011 Mavericks and the 2020 Heat used zone in the
  Finals.
- **Presses.** Full-court traps (2-2-1, run and jump) are rare in the NBA
  outside late-game situations.

## Defensive personnel

| Role | What he does | Signature in the data |
|---|---|---|
| Rim protector | Deters and contests shots at the rim | BLK%, rim attempts allowed and defended rim FG% |
| Drop big | Rim protection from a fixed spot | Great rim numbers, gets hunted in space in the playoffs |
| Switchable big | Guards the perimeter and the post | Matchups spread across positions |
| Point-of-attack defender | Guards the handler, fights through screens | Matchups against high-usage creators |
| Wing stopper | Guards the best perimeter scorer | Opponent usage and efficiency in matchups |
| Roamer or helper | Free safety off a non-shooter | Deflections, steals, DRB%, blocks on help |

**The weak link.** Offenses find the worst defender on the floor and screen
him into the action. In the playoffs this becomes the main tactic, so a
player who cannot be hidden can lose a team minutes even if he helps on
offense.

## Measuring defense

- **Box score.** Steals, blocks, defensive rebounds, and fouls. Steals and
  blocks are real but reward risk-taking, and a gamble that misses shows up
  in nobody's line. Defensive rebounds are mostly the team's.
- **Team defense is measurable.** Opponent four factors, opponent shot
  profile (rim attempts and threes allowed), opponent free throw rate,
  and defensive rating are reliable at the team level.
- **Individual defense is hard to measure.** Oliver's defensive rating and
  defensive win shares split team defense by minutes and box stats. Use
  RAPM-family defensive components (`d_rapm`), matchups
  (`nba.matchups_season` from 2017-18), closest-defender data, rim
  protection, and hustle stats, and state the uncertainty.
- **Opponent shooting percentages are mostly noise.** Especially from
  three. A defense shows its quality in how few good shots it allows, not
  in whether the open ones miss.
- **Matchup data credits the assigned defender.** Help, switches, and
  scheme blur who was responsible. A center's matchups in a switch scheme
  look nothing like those in a drop scheme.

## Rule changes that moved defense

- **2001-02.** Zones legal, defensive three seconds added. Strong-side
  overload defense, loading help toward the ball (Tom Thibodeau's 2007-08
  Celtics), became possible.
- **2004-05.** Hand-checking on the perimeter enforced as a foul. Guards
  became much harder to contain and drive-and-kick offense rose.
- **2018-19.** Freedom of movement emphasis on off-ball holding.
- **2021-22.** Fouls no longer called on non-basketball moves by shooters,
  which lowered free throw rates for foul-drawing scorers.
- **2022-23.** The take foul to stop a transition break draws a free throw
  and possession.
