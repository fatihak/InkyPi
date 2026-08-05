# Pi Weather Display (standalone renderer)

`pi_weather_display/` is a lightweight alternative to the full InkyPi app, for
when you only want the weather plugin and don't need the web UI, plugin
system, or playlist/rotation scheduling. It's aimed at hardware too weak to
run headless Chromium (e.g. a Raspberry Pi Zero W).

## How it differs from the full app

| | Full InkyPi app | `pi_weather_display` |
| --- | --- | --- |
| Rendering | Flask/Jinja HTML+CSS, screenshotted via headless Chromium | Drawn directly with Pillow - no browser |
| Scope | All plugins, web UI, playlists/scheduling | Weather only, no UI |
| Runs as | Long-running `inkypi.service` | One-shot script fired by a systemd timer |
| Config | Web UI, `device.json` | Edit `pi_weather_display/config.py` directly |
| Target hardware | Pi 4/3/Zero 2 W | Also suitable for the original Pi Zero W |

The two are independent - installing one doesn't affect the other, and you
only need one of them for a given display.

## Architecture

- `weather_data.py` - fetches and parses Open-Meteo data (ported from the
  main app's `weather.py`, Open-Meteo only)
- `layout.py` - fixed pixel regions for the 800x480 canvas
- `canvas.py` - orchestrates one full render
- `widgets/` - gauge, chart, forecast-card, and icon/humidity-drop drawing
- `display/inky_driver.py` - same `inky` library call the full app uses;
  `display/mock_driver.py` saves to a file instead, for local testing
- `main.py` - fetch -> render -> display, no Flask, no scheduling loop

See `pi_weather_display/TODO.md` for known bugs and rough edges (e.g. the
current font has no CJK glyph fallback).

## Installing on a Raspberry Pi

```bash
git clone https://github.com/fatihak/InkyPi.git
cd InkyPi
sudo bash install/install-pi-weather-display.sh
```

This installs its own minimal Python virtual environment (Pillow, requests,
pytz, astral, inky - see `install/pi-weather-display-requirements.txt`),
enables SPI, and sets up a `pi-weather-display.timer` systemd unit that runs
the renderer every 10 minutes.

**Before the first real render, edit `pi_weather_display/config.py`** to set
your location (`latitude`/`longitude`) and preferences - there's no web UI to
do this through.

Useful commands after installing:

```bash
systemctl status pi-weather-display.timer     # confirm the timer is active
journalctl -u pi-weather-display.service      # view render logs
sudo systemctl start pi-weather-display.service  # force an immediate render
```

To uninstall: `sudo bash install/uninstall-pi-weather-display.sh` (removes the
service, timer, and venv - leaves your git checkout alone).

## Local testing (no hardware required)

```bash
python pi_weather_display/main.py --mock-output path/to/output.png
```

This runs the full fetch -> render pipeline and saves the result to a PNG
instead of driving a real display - works on Windows/macOS/Linux, no `inky`
package needed.
