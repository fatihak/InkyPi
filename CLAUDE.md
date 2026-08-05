# Project workflow & standing rules

This file documents the standing workflow rules for working on InkyPi (in particular the
weather plugin, and the standalone `pi_weather_display/` renderer) in this repo. Follow
these automatically, without being asked each time.

## Dev environment

- Local Windows dev server: `.\inkyenv\Scripts\python.exe src\inkypi.py --dev`, served at
  `http://localhost:8080`.
- **The dev server must be restarted after every `.html` / `.css` / `.py` change.** It runs
  via `waitress.serve`, not Flask's dev reloader, so `TEMPLATES_AUTO_RELOAD` is off and
  Jinja templates are cached in memory — edits will not show up on refresh otherwise.
  Restart pattern:
  ```powershell
  Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue |
    Select-Object -Property OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
  .\inkyenv\Scripts\python.exe src\inkypi.py --dev
  ```
- To render/test a plugin without clicking through the UI, POST to the same endpoint the
  "Update Now" button calls: `POST /update_now` with form fields matching the plugin's
  settings (e.g. `plugin_id=weather`, `latitude`, `longitude`, `units`, `weatherProvider`,
  etc.) — this exercises the real code path (`generate_image` -> `display_manager`), not a
  bypass.
- `pi_weather_display/` (the standalone Pillow-based renderer) has no dev server — test it
  directly: `.\inkyenv\Scripts\python.exe pi_weather_display\main.py --mock-output <path>`.

## Visual/icon mockups

- When generating a preview image of a new icon or visual change, save it to
  `mock_display_output/` in the repo root with a descriptive filename, and **leave it
  there** — don't clean these up. They're a kept record of each iteration for comparison.
- That folder is organized into subfolders: `pi_zero/` (standalone renderer test images),
  `icon_overviews/` (icon comparison/showcase grids), `pi4/` (everything from the
  Chromium/CSS-rendered Pi 4 dithering work). Put new renders in whichever fits, or a new
  subfolder if it's a genuinely new category.

## Bugs / ideas tracking

- `pi_weather_display/TODO.md` tracks known bugs and polish items for the standalone
  renderer. Add to it when something rough turns up; check items off (don't delete them)
  once fixed.

## Install procedure

- The full app and `pi_weather_display/` each have their own independent install path in
  `install/` — installing one doesn't affect the other:
  - Full app: `install.sh` / `update.sh` / `uninstall.sh`, using `requirements.txt` /
    `requirements-dev.txt` / `debian-requirements.txt` (+ `ws-requirements.txt` for
    Waveshare displays), installs to `/usr/local/inkypi`, runs as `inkypi.service`.
  - `pi_weather_display/`: `install-pi-weather-display.sh` / `uninstall-pi-weather-display.sh`,
    using `pi-weather-display-requirements.txt` / `pi-weather-display-debian-requirements.txt`,
    installs to `/usr/local/pi-weather-display`, runs periodically via
    `pi-weather-display.timer` (not a long-running service).
  - Keep both requirements files' shared package versions (pillow, requests, pytz, astral)
    in sync with the main `requirements.txt` when bumping one.
  - See [docs/pi_weather_display.md](./docs/pi_weather_display.md) for full details.

## Raspberry Pi compatibility

- The real deployment target is a Raspberry Pi (currently Pi 4/5, Raspberry Pi OS, ARM) —
  or, for `pi_weather_display/`, potentially a Pi Zero W / ESP32-S3 — **not** the Windows
  dev server, which is a local convenience only. Before considering a change done, check
  whether it depends on anything OS-specific (path separators, an assumed binary name, a
  Windows-only tool) versus standard cross-platform behavior.
- Browser-rendered templates (the original Flask/Jinja/Chromium plugin path) go through
  headless Chromium (`src/utils/image_utils.py: _find_chromium_binary()`, checks
  `chromium-headless-shell`, `chromium`, `chrome` in that order). Confirm whatever binary
  name is assumed is actually what's installed on Raspberry Pi OS
  (`chromium` / `chromium-headless-shell` via `apt install chromium`). This does not apply
  to `pi_weather_display/`, which renders natively with Pillow and has no browser
  dependency at all.

## Git workflow — commit, push, deploy to the Pi, verify on the real display

> **PAUSED as of 2026-08-05**: steps 3-5 below (push / pull-on-Pi / restart service /
> verify on the real display) are on hold. The user said: *"it is now no longer needed to
> update or run the code on the raspberry pi, we are now switching back to running on this
> local windows machine."* Until told to resume, **local dev-server / mock-driver testing
> is the final test**, not just the initial one — don't push to the Pi or touch
> `inkypi.service` unless asked. Steps 1-2 (local test, commit per major change) still
> apply as normal. This whole section is kept intact so it can be un-paused later.

For each major change:

1. Implement and test locally first (dev server above).
2. **Commit the change** — one commit per major change, with a descriptive message.
3. ~~**Push to `origin`** (SSH remote, see below — HTTPS push is not set up/usable).~~ *(paused)*
4. ~~**Pull the new code onto the Raspberry Pi over SSH**:~~ *(paused)*
   ```
   ssh dorus@192.168.1.183 "cd /home/dorus/InkyPi && git pull"
   ```
4b. ~~**Restart the live service**: `ssh dorus@192.168.1.183 "sudo systemctl restart inkypi.service"`.~~ *(paused)*
   `inkypi.service` is a long-running Python process — `git pull` only updates files on
   disk, it does **not** make the already-running process pick up changed `.py` code.
   (Confirmed: a changed string constant in `weather.py` kept showing its old value through
   `/update_now` until the service was restarted.) When resumed, do this before every
   final-verification step, not only when you know you touched a `.py` file.
5. ~~**Final test = trigger a real update on the Pi's live display**~~ *(paused — for now,
   final test = local dev-server render or `pi_weather_display` mock-driver render)*. The
   Pi's `inkypi.service` runs the real Flask app on port 80 (via the same `/update_now`
   endpoint used locally), backed by the real `device.json` and real display hardware:
   ```
   curl -s -X POST http://192.168.1.183/update_now \
     -d "plugin_id=weather" -d "latitude=51.0004365" -d "longitude=5.8993687" \
     -d "units=metric" -d "weatherProvider=OpenMeteo" -d "displayRefreshTime=true" \
     -d "displayMetrics=true" -d "displayGraph=true" -d "displayRain=true" \
     -d "displayGraphIcons=true" -d "graphIconStep=2" -d "displayForecast=true" \
     -d "forecastDays=5" -d "moonPhase=false" -d "weatherTimeZone=locationTimeZone" \
     -d "textColor=#000000"
   ```
   Then pull back `/home/dorus/InkyPi/src/static/images/current_image.png` via `scp` to
   confirm what's actually now showing on the physical screen.

## Raspberry Pi access

- Host: `192.168.1.183` (hostname `pi4`), user `dorus`. Key-based SSH auth is set up
  (non-interactive `ssh`/`scp` work directly, no password/prompts).
- Repo: `/home/dorus/InkyPi` (same `origin` as this machine). `/usr/local/inkypi/src` is a
  symlink into that clone, so a `git pull` there immediately affects what the live service
  runs on its next update.
- Production venv: `/usr/local/inkypi/venv_inkypi/bin/python3`.
- Live service: systemd unit `inkypi.service` (`ExecStart=/usr/local/bin/inkypi run`,
  runs as root). Check with `systemctl is-active inkypi.service`. Avoid restarting it
  carelessly — it drives the user's actual physical display continuously.
- GitHub push from this machine uses SSH (`git@github.com:...`), not HTTPS — GitHub
  rejects plain password auth for git operations.
