# NBA Lake

Every free NBA dataset in one local database on your own machine, from
1946-47 box scores to play-by-play, shots, lineups, player tracking, awards,
and betting lines, kept in one consistent model. You ask questions in plain
English through Claude Code, and it answers from the data or writes a
shareable report.

[![Watch the NBA Lake trailer](https://img.youtube.com/vi/171T8mto0zc/maxresdefault.jpg)](https://youtu.be/171T8mto0zc)

## Install

You need macOS on Apple silicon (M1 or later) or Linux on x86_64 or arm64
(glibc 2.35 or later, as on Ubuntu 22.04), 50 GB of free disk, and
[Claude Code](https://claude.com/claude-code). In a terminal, run:

```bash
curl -fsSL https://raw.githubusercontent.com/adamMgross/nbagents/main/install.sh | sh
```

This installs two commands, `nbalake` and `nba`, and the Claude Code skills
that drive them. Use the installer rather than downloading an archive from
the Releases page: on macOS a browser download is blocked by Gatekeeper,
and the installer avoids that. Run the same command again to update.

## Use

Open Claude Code and ask it to set up the NBA lake. It downloads about
2.6 GB of public data and builds the database, which takes about an hour.
Keep a laptop plugged in with the lid open until it finishes.

Then ask anything:

- Who has the most playoff wins above replacement since 1974?
- How did Steph Curry's shot chart change from 2013 to 2016?
- Make a report on the best Game 7 performances.

To pick up newer games later, ask Claude Code to update the NBA lake.

## Feedback

Found a wrong number, a missing dataset, or a question it answers badly?
Open an issue. Fixes and additions arrive in the next release, which the
installer picks up.

## Source

Each release commits a snapshot of the source here, under the MIT license.
Pull requests are not merged, since the snapshot is replaced on every
release, so describe a change in an issue instead. With `uv`, `uv sync` and
`uv run pytest` run the test suite. See `ARCHITECTURE.md` for how it is
built.
