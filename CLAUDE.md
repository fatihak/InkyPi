# Project workflow & standing rules

This file documents the standing workflow rules for working on `pi_weather_display/` (the
only app on this branch — see below) in this repo. Follow these automatically, without
being asked each time.

## What's on this branch

This branch (`pi-zero-native-render`) intentionally does **not** have the original
multi-plugin Flask/Chromium InkyPi app (`src/`) — it was removed here so this branch is a
minimal, standalone weather-only renderer. `main` and other branches (`pi-display-testing`,
`Simplify`, `lcd-display-800x480`) still have the full app untouched; this removal is
specific to this branch.

## Dev environment

- No dev server, no web UI. Test locally by rendering to a file:
  `.\inkyenv\Scripts\python.exe pi_weather_display\main.py --mock-output <path>`
- This runs the real fetch -> render pipeline against live Open-Meteo data; no mocking of
  the interesting logic, only the final display step is swapped out.

## Visual/icon mockups

- **Render a fresh screenshot after every update to this app** (not just when a visual
  change was intended) — `--mock-output` to `mock_display_output/pi_zero/` with a
  descriptive or timestamped filename. Do this automatically, without being asked each
  time.
- When generating a preview image of a new icon or visual change, save it to
  `mock_display_output/` in the repo root with a descriptive filename, and **leave it
  there** — don't clean these up. They're a kept record of each iteration for comparison.
- That folder is organized into subfolders: `pi_zero/` (this app's test images),
  `icon_overviews/` (icon comparison/showcase grids), `pi4/` (historical renders from the
  now-removed Chromium/CSS-rendered app, kept for reference). Put new renders in
  whichever fits, or a new subfolder if it's a genuinely new category.

## Bugs / ideas tracking

- `pi_weather_display/TODO.md` tracks known bugs and polish items. Add to it when
  something rough turns up; check items off (don't delete them) once fixed.

## Install procedure

- `install/install-pi-weather-display.sh` / `install/uninstall-pi-weather-display.sh`,
  using `pi-weather-display-requirements.txt` / `pi-weather-display-debian-requirements.txt`.
  Installs to `/usr/local/pi-weather-display`, runs periodically via
  `pi-weather-display.timer` (not a long-running service — a systemd timer firing every
  10 minutes by default).
- See [docs/pi_weather_display.md](./docs/pi_weather_display.md) for full details.

## Raspberry Pi compatibility

- Target hardware is a Raspberry Pi (Zero W and up) driving a Pimoroni Inky Impression
  panel via the `inky` Python library — not the Windows dev environment, which is a local
  convenience only (rendering works cross-platform via `--mock-output`; only the real
  `display/inky_driver.py` path needs actual Pi/Inky hardware).
- No Chromium/browser dependency at all — this was the whole point of the rewrite from the
  original HTML/CSS-rendered app.

## Git workflow — commit, and (when resumed) deploy to a Pi

> **Pi deployment is PAUSED as of 2026-08-05.** The user said: *"it is now no longer
> needed to update or run the code on the raspberry pi, we are now switching back to
> running on this local windows machine."* Until told to resume, **local `--mock-output`
> testing is the final test**, not just the initial one — don't push to or touch any Pi
> unless asked. Commit-per-major-change (below) still applies as normal.

For each major change:

1. Implement and test locally first (`--mock-output` above).
2. **Commit the change** — one commit per major change, with a descriptive message.
3. *(paused)* Push to `origin`, then on the target Pi: `git pull`. Since this is a
   one-shot job (not a long-running process), the *next* scheduled timer tick picks up
   changed code automatically — no service restart needed for plain code changes. Only
   rerun `sudo bash install/install-pi-weather-display.sh` if dependencies or the systemd
   unit files themselves changed (safe to rerun any time).
4. *(paused)* Final test = let a real timer tick happen (or force one with
   `sudo systemctl start pi-weather-display.service`) and confirm the physical display
   updated correctly.

## Raspberry Pi access

- Host: `192.168.1.183` (hostname `pi4`), user `dorus`. Key-based SSH auth is set up
  (non-interactive `ssh`/`scp` work directly, no password/prompts).
- Note: that Pi currently runs the *old* full InkyPi app (`inkypi.service`, from a
  different branch state) — it is not running `pi_weather_display`. Deploying this
  branch's app there would mean cloning/pulling this branch and running
  `install-pi-weather-display.sh` on it, alongside or instead of the existing install.
- GitHub push from this machine uses SSH (`git@github.com:Dorus-Weather/InkyPi.git`), not
  HTTPS — GitHub rejects plain password auth for git operations.
