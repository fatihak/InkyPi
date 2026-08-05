# InkyPi Weather Display

<img src="./docs/images/inky_clock.jpg" />

## About

A weather-only E-Ink display, built for a Raspberry Pi driving a Pimoroni Inky
Impression panel. It renders natively with Pillow (no browser, no Chromium)
and runs as a lightweight, periodic job instead of a long-running web app -
just fetch the forecast, draw it, push it to the display, repeat.

This started as a fork of [fatihak/InkyPi](https://github.com/fatihak/InkyPi),
a full multi-plugin E-Ink dashboard with a web UI. This branch strips that
down to a single purpose: a minimal, low-overhead weather display suitable
for weaker hardware (e.g. a Raspberry Pi Zero W) that can't comfortably run a
headless browser.

**Features**:
- Current conditions, an hourly temperature/rain chart, and a multi-day
  forecast, all hand-drawn with Pillow
- No web UI, no plugins, no playlist scheduling - configuration is a single
  Python file
- Runs as a `systemd` timer (e.g. every 10 minutes), not a persistent service
- Weather data from [Open-Meteo](https://open-meteo.com/) - no API key needed

## Hardware

- Raspberry Pi (Zero W, Zero 2 W, 3, or 4)
- MicroSD Card (min 8 GB) like [this one](https://amzn.to/3G3Tq9W)
- E-Ink Display: Inky Impression by Pimoroni
    - **[13.3 Inch Display](https://collabs.shop/q2jmza)**
    - **[7.3 Inch Display](https://collabs.shop/q2jmza)**
    - **[5.7 Inch Display](https://collabs.shop/ns6m6m)**
    - **[4 Inch Display](https://collabs.shop/cpwtbh)**
- Picture Frame or 3D Stand - see [community.md](./docs/community.md) for
  community-submitted 3D models, custom builds, and other frame ideas

**Disclosure:** The links above are affiliate links. I may earn a commission
from qualifying purchases made through them, at no extra cost to you.

## Installation

1. Flash Raspberry Pi OS onto your SD card - see
   [installation.md](./docs/installation.md) for detailed steps.
2. Clone the repository and run the installer:
    ```bash
    git clone git@github.com:Dorus-Weather/InkyPi.git
    cd InkyPi
    sudo bash install/install-pi-weather-display.sh
    ```
3. **Edit `pi_weather_display/config.py`** to set your location
   (`latitude`/`longitude`) and preferences - there's no web UI, so this is
   done directly in the source file.
4. Reboot if the installer enabled SPI for the first time.

The installer sets up its own minimal Python virtual environment and a
`pi-weather-display.timer` systemd unit that renders and updates the display
every 10 minutes. See [pi_weather_display.md](./docs/pi_weather_display.md)
for the full architecture, install details, and local (no-hardware) testing
instructions.

## Update

```bash
cd InkyPi
git pull
sudo bash install/install-pi-weather-display.sh
```

The installer is safe to rerun - it reinstalls the venv dependencies and
refreshes the systemd units in place.

## Uninstall

```bash
sudo bash install/uninstall-pi-weather-display.sh
```

Removes the systemd service/timer and its virtual environment. Your git
checkout (and `config.py`) is left untouched.

## License

Distributed under the GPL 3.0 License, see [LICENSE](./LICENSE) for more
information.

This project includes fonts and icons with separate licensing and
attribution requirements. See [Attribution](./docs/attribution.md) for
details.

## Issues

Check out the [troubleshooting guide](./docs/troubleshooting.md).

If you're using a Pi Zero W, note that there are known issues during
installation - see
[Known Issues during Pi Zero W Installation](./docs/troubleshooting.md#known-issues-during-pi-zero-w-installation)
in the troubleshooting guide.

## Acknowledgements

This project is a fork of [InkyPi](https://github.com/fatihak/InkyPi) by
[fatihak](https://github.com/fatihak) - all credit for the original
multi-plugin app, web UI, and display driver integration goes there. Also
worth checking out:

- [PaperPi](https://github.com/txoof/PaperPi) - supports Waveshare devices
- [InkyCal](https://github.com/aceinnolab/Inkycal) - modular plugins for custom dashboards
- [PiInk](https://github.com/tlstommy/PiInk) - inspiration behind InkyPi's original Flask web UI
- [rpi_weather_display](https://github.com/sjnims/rpi_weather_display) - alternative eink weather dashboard with advanced power efficiency
