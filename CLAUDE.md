# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

InkyPi is a Raspberry Pi application that drives e-ink displays (Pimoroni Inky and Waveshare) through a web-based configuration interface. It uses a plugin system to display various content (weather, calendar, clocks, images, news, etc.) on e-paper screens.

## Development Commands

### Setup (traditional)
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r install/requirements-dev.txt
bash install/update_vendors.sh   # downloads frontend JS dependencies
```

### Setup (devbox/Nix)
```bash
devbox shell
```

### Run in development mode (no hardware required)
```bash
python src/inkypi.py --dev    # serves on http://localhost:8080
# or
devbox run dev
```

Development mode uses a mock display that saves output to `mock_display_output/` as PNG files instead of driving real hardware.

### Run tests
```bash
pytest
# or
devbox run test
```

### Run a single test
```bash
pytest tests/test_model.py::TestClassName::test_function_name
```

## Architecture

### Entry Point and Core Loop

`src/inkypi.py` initializes Flask, creates the `Config`, `DisplayManager`, and `RefreshTask`, registers blueprints, and starts the Waitress WSGI server. The `RefreshTask` (`src/refresh_task.py`) runs as a background daemon thread that periodically calls the active plugin's `generate_image()` and pushes the result to the display.

### Configuration

`Config` (`src/config.py`) reads from `src/config/device.json` (or `device_dev.json` in dev mode). It tracks device settings (display type, resolution, orientation), the ordered plugin list, playlist schedules, and refresh metadata. All persistent state lives in this JSON file.

### Display Abstraction

`src/display/display_manager.py` selects among three backends based on config:
- `inky_display.py` — Pimoroni Inky hardware
- `waveshare_display.py` — Waveshare hardware (requires `install/ws-requirements.txt`)
- `mock_display.py` — Development/testing, saves PNG to disk

### Plugin System

Each plugin lives in `src/plugins/{plugin_id}/` and must contain:
- `{plugin_id}.py` — class inheriting from `BasePlugin`
- `plugin-info.json` — metadata (`id`, `display_name`, class name)
- `icon.png` — displayed in the web UI
- `settings.html` (optional) — Jinja2 form for plugin configuration
- `render/` (optional) — HTML/CSS templates for HTML-to-image rendering

`BasePlugin` (`src/plugins/base_plugin/base_plugin.py`) provides:
- `generate_image(settings, device_config) -> PIL.Image` — **must override**
- `render_image(dimensions, html_file, css_file, template_params)` — renders HTML to PIL image via headless Chromium (use this for complex layouts)
- `generate_settings_template()` — returns dict of settings with defaults
- `cleanup(settings)` — override for resource cleanup

`plugin_registry.py` dynamically loads all plugins at startup via `importlib`.

### Flask Blueprints

Routes are organized in `src/blueprints/`:
- `main.py` — dashboard UI
- `plugin.py` — plugin CRUD and triggering refreshes
- `settings.py` — device settings
- `playlist.py` — time-based display scheduling
- `apikeys.py` — API key management (stored in `.env`)

### Utilities

- `src/utils/image_utils.py` — HTML-to-PNG rendering (headless Chromium), image transformations
- `src/utils/image_loader.py` — adaptive image loading with device resolution awareness
- `src/utils/http_client.py` — HTTP request wrapper
- `src/utils/app_utils.py` — general helpers

## Adding a New Plugin

1. Create `src/plugins/{plugin_id}/` directory
2. Create `plugin-info.json` with `id`, `display_name`, and `class` fields
3. Create `{plugin_id}.py` with a class extending `BasePlugin` implementing `generate_image()`
4. Optionally add `settings.html` for configuration and `render/` for HTML templates
5. Add an `icon.png`

See `docs/building_plugins.md` for detailed plugin development documentation.

## Key Conventions

- Plugin settings are passed as a dict to `generate_image()`; use `settings.get("key", default)` for safe access
- `device_config` passed to `generate_image()` exposes display dimensions (`.width`, `.height`) and color mode
- Images returned from `generate_image()` must match display dimensions exactly
- API keys are stored in `.env` and accessed via `python-dotenv`; the web UI manages them through the `/apikeys` blueprint
- The `mock_display_output/` directory is gitignored and used only during development

## Current Development State (last updated 2026-02-22)

### Uncommitted new plugins (not yet in upstream)
These plugins exist locally but have **not been committed to git** yet. They are candidates for a PR to the main InkyPi repo:

| Plugin folder | Status | Notes |
|---|---|---|
| `src/plugins/adguard_home/` | Ready | AdGuard Home stats dashboard — see below |
| `src/plugins/history_today/` | Ready | Historical events for today |
| `src/plugins/joke_of_day/` | Ready | Daily joke |
| `src/plugins/moon_phase/` | Ready | Lunar phase display |
| `src/plugins/top_stories/` | Ready | News aggregation |

Also uncommitted: `scripts/make_adguard_icon.py` (helper script to generate the AdGuard icon).

### AdGuard Home plugin — design decisions
- `src/plugins/adguard_home/` displays DNS stats from an AdGuard Home instance
- **SSL verification is always disabled** (`verify=False` on all requests) — this is intentional so the plugin works with domains behind Nginx Proxy Manager using self-signed certificates, without needing a toggle
- Bar colors (total queries background, blocked queries) are **user-configurable** via `<input type="color">` in settings; defaults are `#cccccc` and `#c62828`
- Colors are injected as CSS custom properties (`--color-blocked`, `--color-total`) via a `<style>` block in the Jinja2 template, so the CSS file uses `var(--color-blocked)` / `var(--color-total)` everywhere

### Uncommitted modifications to existing plugins
- `src/plugins/finance_tracker/` — modified (finance_tracker.py, render/finance_tracker.html, settings.html)

### `src/config/device.json`
This file is **not gitignored** by default but contains device-specific configuration. Do not commit it — it holds the local device state (which plugins are enabled, playlist config, etc.).
