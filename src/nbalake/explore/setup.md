---
name: nba-lake-setup
<!-- repo -->
description: Build the NBA lake on a new machine from a fresh clone of this repo, or update it with newer games later. Use when the person asks to set up, install, build, download, or update the NBA data, or when nba or nbalake reports "no lake at".
<!-- end -->
<!-- app -->
description: Build the NBA lake on this machine with the installed nbalake app, or update it with newer games later. Use when the person asks to set up, install, build, download, or update the NBA data, or when nba or nbalake reports "no lake at".
<!-- end -->
---

# Set up the NBA lake

The person you are working for may not be technical. Run every command
yourself, keep them posted in plain words, and never ask them to type into a
terminal. Once the lake is built, the `nba-lake` skill answers their
questions.

<!-- repo -->
You are using the lake, not developing it. Skip the session protocol in
`CLAUDE.md`: no tickets, no edits to the repo, no commits, no pushes.
<!-- end -->

## Requirements

| Need | Notes |
|---|---|
<!-- repo -->
| macOS or Linux | Windows only inside WSL |
| `git` | on macOS it comes with the Xcode Command Line Tools |
| `uv` | installs Python 3.13 and every package itself, https://docs.astral.sh/uv/ |
<!-- end -->
<!-- app -->
| macOS on Apple silicon, or Linux | Linux on x86_64 or arm64 with glibc 2.35 or later, as on Ubuntu 22.04 |
<!-- end -->
| 50 GB free disk | where the lake lives, `~/.local/share/nbalake` unless `NBALAKE_ROOT` says otherwise |
| internet | about 2.6 GB of downloads, no accounts or keys |
| 4 GB of RAM to spare | each build step caps DuckDB at 4 GB |

<!-- repo -->
If `git` or `uv` is missing, tell the person which one and where its install
page is, then stop. `nbalake setup` checks the platform and the disk itself.
<!-- end -->
<!-- app -->
The installer put `nbalake` and `nba` in `~/.local/bin`. If the shell
cannot find them, run them by that path: `~/.local/bin/nbalake` and
`~/.local/bin/nba`. `nbalake setup` checks the platform and the disk itself.
<!-- end -->
`GITHUB_TOKEN` is optional and not needed for a build.

## Build

<!-- repo -->
1. From the repo root run `uv sync`.
2. Tell the person the download takes about 20 minutes on a fast
   connection and building the tables takes longer after that, and on a
   laptop to keep it plugged in with the lid open until it finishes.
3. Run the build in the background with its output in a log. On macOS,
   `caffeinate -i` keeps the machine awake while it runs:

   ```bash
   caffeinate -i uv run nbalake setup > setup.log 2>&1   # macOS
   uv run nbalake setup > setup.log 2>&1                 # Linux
   ```

4. The log stays quiet while files download, because progress bars only draw
<!-- end -->
<!-- app -->
1. Tell the person the download takes about 20 minutes on a fast
   connection and building the tables takes longer after that, and on a
   laptop to keep it plugged in with the lid open until it finishes.
2. Run the build in the background with its output in a log under the
   lake's parent folder. On macOS, `caffeinate -i` keeps the machine awake
   while it runs:

   ```bash
   mkdir -p ~/.local/share
   caffeinate -i nbalake setup > ~/.local/share/nbalake-setup.log 2>&1   # macOS
   nbalake setup > ~/.local/share/nbalake-setup.log 2>&1                 # Linux
   ```

3. The log stays quiet while files download, because progress bars only draw
<!-- end -->
   in a terminal. Measure progress by the lake's size instead:
   `du -sh ~/.local/share/nbalake/raw ~/.local/share/nbalake/data`. `raw`
   grows to about 2.6 GB while downloading, then `data` grows to about
   11 GB while tables build. Report each phase as it finishes.
<!-- repo -->
5. Read the exit code and the last lines of the log.
<!-- end -->
<!-- app -->
4. Read the exit code and the last lines of the log.
<!-- end -->

| Exit | Last line | Do |
|---|---|---|
| 0 | `ready: N games from 1947 to ...` | done, go to Check |
| 1 | `setup stopped. Rerun nbalake setup to resume, ...` | a download or load failed. Rerun the same command. Finished work is kept, so it resumes. If the same file fails three times, stop and tell the person to send the `failed` lines to the repo owner, since setup builds tables only once every file is in |
| 1 | a `gate ... FAIL` line | a data quality check failed on new upstream data. Do not rerun. Tell the person to send the gate lines to the repo owner |
| 2 | a disk or platform message | tell the person what it says, in plain words |
| 75 | `another nbalake write is running` | a build is already running. Wait for it |

## Check

```bash
uv run nba sql "select player, round(neutral_wins, 1) from career_era_wins() limit 3"
```

LeBron James should be first. Upstream sources revise old data now and then,
so numbers can differ slightly from the owner's lake.

## After

- To answer a basketball question, use the `nba-lake` skill.
- To pick up newer games, run `uv run nbalake refresh`, the same way as the
  build. Only new upstream files download, so it takes minutes, not hours.
<!-- app -->
- To update the app itself, run the installer again:
  `curl -fsSL https://raw.githubusercontent.com/adamMgross/nbagents/main/install.sh | sh`.
  The lake is kept.
<!-- end -->
- Never edit the lake's files by hand.
