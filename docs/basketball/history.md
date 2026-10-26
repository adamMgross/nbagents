# History of the game and its numbers

Eras, the rules that made them, the league environment in each, what was
recorded when, and how basketball analytics developed. Read
[README.md](README.md) first.

## Eras

| Seasons | Era | What defined it |
|---|---|---|
| 1946-47 to 1953-54 | BAA and early NBA | No shot clock, stalling, George Mikan's Lakers. The BAA became the NBA in 1949-50. The Pistons beat the Lakers 19-18 in 1950 |
| 1954-55 to 1966-67 | Shot clock and the Celtics | The 24-second clock lifted scoring at once. Bill Russell's Celtics won 11 titles in 13 seasons. Wilt Chamberlain averaged 50.4 points in 1961-62 at a pace near 126 |
| 1967-68 to 1975-76 | Expansion and the ABA | A rival league with the three-point line from its start split the talent. Kareem Abdul-Jabbar. The 1976 merger brought the Nuggets, Pacers, Nets, and Spurs |
| 1976-77 to 1989-90 | Magic, Bird, and the merged league | The NBA three-point line in 1979-80, barely used at first. Showtime, the Celtics, then the Bad Boys Pistons |
| 1990-91 to 1997-98 | Jordan and the physical game | Six Bulls titles, hand-checking, isolation and post play, slowing pace. A shorter three-point line from 1994-95 to 1996-97 |
| 1998-99 to 2003-04 | The dead-ball years | The 1999 lockout, the lowest pace and scoring since the shot clock, Duncan's Spurs and the Shaq and Kobe Lakers |
| 2004-05 to 2011-12 | Perimeter freedom | Hand-checking gone, the Seven Seconds or Less Suns, Thibodeau's help defense, the Heat's Big Three. Analytics enter front offices |
| 2012-13 to 2019-20 | Pace and space | The three-point revolution: the Warriors (73-9 in 2015-16), Morey's Rockets, switch-everything defense, the long two disappears |
| 2020-21 on | Heliocentric stars and skilled bigs | MVPs for Jokic, Embiid, and Gilgeous-Alexander, record offensive efficiency, the play-in, the NBA Cup |

## Rule changes that move the data

| Season | Change | What it does to the numbers |
|---|---|---|
| 1951-52 | Lane widened from 6 to 12 feet | Fewer post camps under the rim |
| 1954-55 | 24-second shot clock, team foul limit and bonus | Pace and scoring jump at once |
| 1964-65 | Lane widened to 16 feet | Partly a response to Chamberlain |
| 1967-68 | ABA starts with a three-point line | ABA stats are not NBA stats |
| 1979-80 | NBA three-point line, 23 ft 9 in, 22 ft in the corners | Threes exist from here |
| 1994-95 | Line shortened to 22 feet all around, restored in 1997-98 | A three-point spike for three seasons |
| 1997-98 | Restricted area arc | Charges inside it become blocks |
| 1998-99 | Lockout, 50 games | Small sample, rusty players |
| 2001-02 | Illegal defense abolished, zones legal, defensive three seconds, 8-second backcourt | Help defense and strong-side overloads |
| 2004-05 | Hand-checking on the perimeter enforced | Drives, free throws, and scoring rise |
| 2011-12 | Lockout, 66 games | Compressed schedule, more back-to-backs |
| 2016-17 | Away-from-the-play foul rule extended to the last two minutes of every quarter | Ends most deliberate fouling of poor free throw shooters |
| 2018-19 | Shot clock resets to 14 after an offensive rebound, freedom of movement | More possessions, faster pace |
| 2019-20 | Coach's challenge. Season suspended, finished in the Orlando bubble | 172 neutral-site games, flagged in `nba.games.neutral_site` |
| 2020-21 | 72 games, limited crowds, play-in tournament | Home edge at a low, a new season type |
| 2021-22 | No fouls for non-basketball moves by shooters | Free throw rates fall for foul drawers |
| 2022-23 | Transition take foul penalized | Fewer intentional fouls on breaks |
| 2023-24 | 65 games for most awards, the NBA Cup | Cup games count in the standings except the final |

## League environment

NBA regular seasons from Basketball-Reference team tables (lake). Pace and
offensive rating before 1973-74 are Basketball-Reference estimates without
offensive rebounds, and before 1968-69 without turnovers. 3PA is per team game.

| Season | Teams | PPG | Pace | ORtg | TS% | 3PA | 3PA/FGA | FTA/FGA |
|---|---|---|---|---|---|---|---|---|
| 1950 | 17 | 80.0 | | | 41.0 | | | 39.7 |
| 1955 | 9 | 93.1 | 102.9 | 89.8 | 45.5 | | | 41.6 |
| 1962 | 9 | 118.8 | 126.2 | 93.6 | 47.9 | | | 34.4 |
| 1970 | 14 | 116.7 | 117.1 | 99.1 | 51.1 | | | 33.9 |
| 1975 | 18 | 102.6 | 104.5 | 97.6 | 50.2 | | | 27.6 |
| 1980 | 22 | 109.3 | 103.1 | 105.3 | 53.1 | 2.8 | 3.1 | 30.7 |
| 1985 | 23 | 110.8 | 102.1 | 107.9 | 54.3 | 3.1 | 3.5 | 33.0 |
| 1990 | 27 | 107.0 | 98.3 | 108.1 | 53.7 | 6.6 | 7.6 | 32.7 |
| 1995 | 27 | 101.4 | 92.9 | 108.2 | 54.3 | 15.3 | 18.8 | 33.2 |
| 1999 | 29 | 91.6 | 88.9 | 102.2 | 51.1 | 13.2 | 16.8 | 33.0 |
| 2004 | 29 | 93.4 | 90.1 | 102.9 | 51.6 | 14.9 | 18.7 | 30.3 |
| 2008 | 30 | 99.9 | 92.4 | 107.5 | 54.0 | 18.1 | 22.2 | 30.6 |
| 2012 | 30 | 96.3 | 91.3 | 104.6 | 52.7 | 18.4 | 22.6 | 27.6 |
| 2015 | 30 | 100.0 | 93.9 | 105.6 | 53.4 | 22.4 | 26.8 | 27.3 |
| 2019 | 30 | 111.2 | 100.0 | 110.4 | 56.0 | 32.0 | 35.9 | 25.9 |
| 2023 | 30 | 114.7 | 99.1 | 114.8 | 58.1 | 34.2 | 38.7 | 26.6 |
| 2026 | 30 | 115.6 | 99.4 | 115.8 | 58.1 | 37.0 | 41.5 | 26.4 |

Turnovers per play fell from 16.3 percent in 1974-75 to 12.7 in 2025-26,
and offensive rebound rate from 33.5 percent in 1979-80 to 22.5 in 2019-20
before rising to 26.0 in 2025-26 (lake).

Shot mix in regular seasons from `nba.shots` (lake), share of field goal
attempts and points per shot:

| Season | Rim 0-3 ft | 4-13 ft | Long two 14 ft+ | Three |
|---|---|---|---|---|
| 1998 | 32.4, 1.22 | 22.8, 0.73 | 28.9, 0.80 | 16.0, 1.04 |
| 2005 | 31.2, 1.18 | 18.6, 0.77 | 30.7, 0.80 | 19.6, 1.07 |
| 2012 | 30.8, 1.23 | 20.1, 0.75 | 26.5, 0.78 | 22.6, 1.05 |
| 2019 | 31.4, 1.28 | 19.8, 0.80 | 13.0, 0.81 | 35.9, 1.07 |
| 2026 | 26.0, 1.37 | 24.3, 0.90 | 8.2, 0.83 | 41.5, 1.08 |

Home teams' regular season win rate by decade, every league in
`nba.team_games` (lake): 1950s 65.4, 1960s 60.3, 1970s 63.6, 1980s 64.9,
1990s 61.4, 2000s 60.5, 2010s 59.0, 2020s 55.1. The 2020 bubble games are
neutral but carry a home team.

## What was recorded when

From `nba.recorded_from` and the lake's coverage. Before a stat's first
season it is missing, not zero.

| From | NBA stat |
|---|---|
| 1946-47 | Points, field goals, free throws, assists, fouls |
| 1950-51 | Rebounds |
| 1951-52 | Minutes |
| 1968-69 | Team turnovers |
| 1973-74 | Offensive and defensive rebounds, steals, blocks. Team possessions become computable, and Basketball-Reference's per 100 and BPM start, estimating player turnovers until 1977-78 |
| 1977-78 | Player turnovers |
| 1979-80 | Three-pointers |
| 1993-94 | Playoff player totals in the lake, summed from box scores |
| 1996-97 | Play-by-play, shot locations, game plus-minus, inactives |
| 2013-14 | Player tracking league-wide (SportVU) |
| 2015-16 | Hustle stats and Synergy play types |
| 2017-18 | Matchups (Second Spectrum tracking) |

`nba coverage <table or words>` answers this per table and season type.

## How the analysis of basketball developed

- **Counting stats and per game.** For decades players were judged by
  points, rebounds, and assists per game, and scoring titles. Linear weights
  formulas like TENDEX and the NBA's efficiency stat summed the box score.
- **Possessions.** Dean Oliver built possession-based ratings and the four
  factors through the 1990s and published Basketball on Paper in 2004, the
  year he joined the SuperSonics. John Hollinger's PER and his annual
  prospectus books brought per-minute, pace-adjusted stats to fans.
- **Plus-minus.** Winston and Sagarin's adjusted plus-minus for the
  Mavericks, Rosenbaum's public APM (2004), and Sill's RAPM (2010) moved
  evaluation from the box score to the scoreboard.
- **Front offices.** Daryl Morey became the Rockets' general manager in
  2007, the year the MIT Sloan Sports Analytics Conference started. By the
  mid 2010s every team had an analytics staff.
- **Spatial data.** Kirk Goldsberry's shot charts (2012) made the value of
  shot location visible. SportVU cameras reached every arena in 2013-14,
  Second Spectrum took over in 2017-18, and Sony's Hawk-Eye from 2023-24.
- **Public impact metrics.** Basketball-Reference's Win Shares and BPM,
  ESPN's RPM (2014), FiveThirtyEight's RAPTOR (2019), then EPM, LEBRON, and
  DARKO. Cleaning the Glass popularized filtering garbage time.
- **What the analytics changed on the floor.** The rim, three, and free
  throw shot diet, the death of the long two, load management, switching
  defenses, and the value of shooting at every position.

## Comparing across eras

- Compare against each season's league, not raw numbers. Relative true
  shooting and per 100 rates first.
- Pace alone does not fix 1960s rebounds. More missed shots meant more
  rebounds, and rebound rate cannot be computed before 1973-74.
- League strength varies: talent split by the ABA, diluted by expansion
  (11 teams in 1946-47, 30 from 2004-05), deepened by integration and
  international players.
- Rules change what a skill is worth. A post scorer in 1993 and a pull-up
  shooter in 2023 are each the best answer to their own rules.
- For a translated value, use the lake's `era_wins` metric and quote its
  version.
