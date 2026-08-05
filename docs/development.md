# Development Quick Start

## Development Without Hardware

`pi_weather_display` needs no Raspberry Pi, no physical display, and no root
access to develop against - it's a plain Python script that renders to a PNG
file. Works on **Windows**, **macOS**, and **Linux**.

## Setup

```bash
# 1. Clone and set up a virtual environment
git clone git@github.com:Dorus-Weather/InkyPi.git
cd InkyPi
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. Install dependencies (the minimal set - no inky needed for local testing)
pip install pillow requests pytz astral

# 3. Render to a file instead of a real display
python pi_weather_display/main.py --mock-output output.png
```

**That's it!** Open `output.png` to see the result.

## What You Can Do

- **Iterate on layout/widgets** - edit `layout.py` or anything under
  `widgets/`, rerun the command above, check the PNG
- **Test different locations/conditions** - edit the `DisplayConfig`
  defaults in `config.py` (or construct one with different
  `latitude`/`longitude` in a throwaway script) and rerun
- **Debug data parsing** - `weather_data.fetch_snapshot()` hits the live
  Open-Meteo API directly; add a `print()`/breakpoint and rerun

## Development Tips

1. Save preview renders to `mock_display_output/` with a descriptive
   filename, and leave them there - it's a kept record of iterations for
   comparison, not a scratch folder.
2. Check `pi_weather_display/TODO.md` before starting on something - it may
   already be a known issue.
3. There's no hot reload - it's a one-shot script, just rerun it.

## Testing Against Real Hardware

Once you have access to a Raspberry Pi with an Inky Impression display, see
[pi_weather_display.md](./pi_weather_display.md) for the full install
(`install/install-pi-weather-display.sh`), which additionally installs the
`inky` package and sets up the systemd timer. Local mock-driver testing
should still be your first pass before deploying to real hardware.
