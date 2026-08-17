# InkyPi Development Quick Start

## Development Without Hardware

The `--dev` flag enables complete development without requiring:

- Raspberry Pi hardware
- Physical Waveshare e-ink display
- Root privileges or GPIO access
- Linux-specific features (systemd)

Works on **macOS**, **Linux**, and **Windows** - no hardware needed!

## Setup

```bash
# 1. Clone and setup
git clone https://github.com/Pirito10/InkyPi-Zero.git
cd InkyPi-Zero

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install Python dependencies and run
pip install -r install/requirements-dev.txt
bash install/update_vendors.sh
python src/inkypi.py --dev
```

**That's it!** Open http://localhost:8080 and start developing.

## What You Can Do

- **Develop plugins** - Create new plugins without hardware (no Raspberry Pi, nor physical displays)
- **Test UI changes** - Instant feedback on web interface modifications  
- **Debug issues** - Full error messages in terminal
- **Verify rendering** - Check output in `mock_display_output/latest.png`
- **Cross-platform development** - Works on macOS, Linux, Windows

## Essential Commands

```bash
source .venv/bin/activate            # Activate virtual environment
python src/inkypi.py --dev           # Start development server
deactivate                           # Exit virtual environment
```

## Development Tips

1. **Check rendered output**: Images are saved to `mock_display_output/`
2. **Plugin development**: Copy an existing plugin as template (e.g., `clock/`)
3. **Configuration**: Edit `src/config/device_dev.json` for display settings
4. **Hot reload**: Restart server to see code changes

## Testing Your Changes

1. Configure a plugin through the web UI
2. Click "Display" button
3. Check `mock_display_output/latest.png` for result
4. Iterate quickly without deployment

## Other Requirements

InkyPi relies on system packages for some features, which are normally installed via the `install.sh` script.

### Linux

The required packages can be found in this file:

[install/debian-requirements.txt](../install/debian-requirements.txt)

Use your favourite package manager (such as `apt`) to install them.

### Chromium or Google Chrome browser

InkyPi uses `--headless` mode to render HTML templates to PNG images using a Chrome-like browser.

Different platforms have different available browser packages, refer to the recommended packages in the table below:

| Platform | Recommended Package | Notes |
| --- | --- | --- |
| Raspbian / Debian | chromium-headless-shell | chromium or google-chrome will also work if in PATH |
| All other Linux | chromium | |
| macOS | Google Chrome | chromium on macOS / aarch64 is not considered stable |
| Windows | Chromium or Google Chrome | should also work if in PATH |

InkyPi will search for a Chrome-like browser in your system's PATH.
