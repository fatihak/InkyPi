# Pi Weather Display

Architecture, install, and local-testing details for `pi_weather_display/` -
the renderer this project is built around. See the root
[README.md](../README.md) for hardware and the quick install steps.

## Design

- Renders natively with Pillow - no browser, no Chromium, no HTML/CSS.
- No web UI, no plugin system, no playlist/scheduling. One plugin (weather),
  one config file, one job.
- Runs as a `systemd` timer firing periodically (default every 10 minutes),
  not a long-running service - a crashed run just gets retried on the next
  tick, no supervisor logic needed.
- Chosen over an ESP32-S3/embedded-C rewrite because it reuses Pimoroni's
  existing `inky` Python display driver unchanged, and reuses the weather
  data-fetch/parsing logic almost verbatim, rather than reimplementing the
  whole visual layout in C.

## Architecture

- `weather_data.py` - fetches and parses Open-Meteo data (current, hourly,
  daily forecast, air quality/UV) into typed dataclasses
- `layout.py` - fixed pixel regions for the 800x480 canvas
- `canvas.py` - orchestrates one full render (`WeatherCanvas.render()`)
- `widgets/` - gauge (wind/pressure/UV/AQI), chart (temp/rain), forecast-card,
  and icon/humidity-drop drawing - all hand-drawn with Pillow
- `display/inky_driver.py` - thin wrapper around the `inky` library;
  `display/mock_driver.py` saves to a file instead, for testing without
  hardware
- `assets/` - the icon PNGs and Jost font files it actually uses (see
  [attribution.md](./attribution.md))
- `config.py` - a plain dataclass (location, units, refresh interval, etc.) -
  edited directly in source, since there's no web UI
- `main.py` - fetch -> render -> display, no scheduling loop of its own
  (that's the systemd timer's job)
- `TODO.md` - known bugs and rough edges (e.g. the current font has no CJK
  glyph fallback)

## Installing on a Raspberry Pi

```bash
git clone git@github.com:Dorus-Weather/InkyPi.git
cd InkyPi
sudo bash install/install-pi-weather-display.sh
```

This installs its own minimal Python virtual environment (Pillow, requests,
pytz, astral, inky - see `install/pi-weather-display-requirements.txt`),
enables SPI, and sets up a `pi-weather-display.timer` systemd unit.

**Before the first real render, edit `pi_weather_display/config.py`** to set
your location and preferences.

Useful commands after installing:

```bash
systemctl status pi-weather-display.timer     # confirm the timer is active
journalctl -u pi-weather-display.service      # view render logs
sudo systemctl start pi-weather-display.service  # force an immediate render
```

To update: `git pull` then rerun `install-pi-weather-display.sh` (safe to
rerun - reinstalls deps and refreshes the systemd units in place).

To uninstall: `sudo bash install/uninstall-pi-weather-display.sh` (removes
the service, timer, and venv - leaves your git checkout alone).

## Local testing (no hardware required)

```bash
python pi_weather_display/main.py --mock-output path/to/output.png
```

This runs the full fetch -> render pipeline and saves the result to a PNG
instead of driving a real display - works on Windows/macOS/Linux, no `inky`
package needed.
