# InkyPi Development Guide for AI Agents

This file contains guidelines and conventions for agentic coding agents working on the InkyPi e-ink display project.

## Project Overview

InkyPi is a Flask-based web application for managing content on e-ink displays (Pimoroni Inky, Waveshare EPD). It features a plugin architecture, web UI, and REST API for displaying various content types (weather, calendar, news, etc.) on low-power e-ink displays.

## Commands and Development Workflow

### Installation and Setup
```bash
# Production installation (includes hardware dependencies)
sudo bash install/install.sh

# Development installation (no hardware required)
pip install -r install/requirements.txt
pip install -r install/requirements-dev.txt
```

### Development
```bash
# Run development server with live reload (no display hardware needed)
python src/inkypi.py --dev

# Production server (requires display hardware)
python src/inkypi.py
```

### Testing
```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_model.py -v

# Run with coverage (if available)
pytest tests/ --cov=src

# Test specific plugin
python scripts/test_plugin.py
```

### Code Quality
Note: No formal linting/formatting tools configured. Consider adding:
```bash
# If adding black for formatting
black src/ tests/

# If adding flake8 for linting
flake8 src/ tests/

# If adding mypy for type checking
mypy src/
```

## Code Style Guidelines

### Python Conventions
- **Indentation:** 4 spaces (configured in .editorconfig)
- **Line endings:** LF (Unix style)
- **Encoding:** UTF-8
- **Max line length:** Not strictly enforced, aim for 88-120 characters
- **Trailing whitespace:** Always trim
- **Final newline:** Required

### Naming Conventions
- **Classes:** PascalCase (`BasePlugin`, `Clock`, `PlaylistManager`)
- **Functions/Variables:** snake_case (`generate_image`, `device_config`)
- **Constants:** UPPER_SNAKE_CASE (`DEFAULT_TIMEZONE`, `CLOCK_FACES`)
- **Files:** snake_case (`weather.py`, `app_utils.py`)
- **Plugin IDs:** snake_case (`weather`, `ai_text`, `nhl_team_schedule`)

### Import Organization
```python
# Standard library imports first
import os
import logging
from datetime import datetime

# Third-party imports
import requests
from PIL import Image
import pytz

# Local imports
from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import resolve_path, get_font
```

### Type Annotations
Not currently used extensively, but encouraged for new code:
```python
from typing import Dict, List, Optional, Union

def generate_image(settings: Dict[str, Any]) -> Image.Image:
    pass
```

## Architecture Patterns

### Plugin Development
All plugins inherit from `BasePlugin` in `src/plugins/base_plugin/base_plugin.py`:

```python
from plugins.base_plugin.base_plugin import BasePlugin

class MyPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        # Plugin initialization
    
    def get_settings_schema(self) -> Dict:
        # Return JSON schema for plugin settings
        pass
    
    def generate_image_content(self, settings: Dict, device_config: Dict) -> Image.Image:
        # Main image generation logic
        pass
```

Each plugin requires a `plugin-info.json`:
```json
{
  "display_name": "Display name for the plugin",
  "id": "plugin_id",
  "class": "PluginClassName"
}
```

### Error Handling Patterns
- Use structured logging: `logger = logging.getLogger(__name__)`
- Always include context in error messages
- Graceful degradation for optional features
- Use try/catch blocks for external API calls

```python
try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()
except requests.RequestException as e:
    logger.error(f"Failed to fetch data from {url}: {str(e)}")
    return None
```

### Configuration Management
- Centralized `Config` class handles persistence
- Use JSON schema for validation
- Environment variables for sensitive data
- Default values in plugin code

### Flask Blueprint Organization
- Each major feature gets its own blueprint
- Route naming: `bp.route('/feature/action')`
- Template organization: `templates/feature/`
- Static assets: `static/feature/`

## File Structure Guidelines

```
src/
├── plugins/                 # Plugin system
│   ├── base_plugin/        # Base plugin class
│   ├── plugin_name/        # Individual plugin folders
│   │   ├── plugin.py      # Main plugin logic
│   │   └── plugin-info.json # Plugin metadata
├── blueprints/             # Flask route handlers
├── utils/                  # Shared utilities
├── config/                 # Configuration management
├── display/                # Display abstraction layer
├── templates/              # Jinja2 templates
└── static/                 # CSS, JS, images
```

## Testing Guidelines

### Test Structure
- Use pytest framework
- Test files: `tests/test_*.py`
- Focus on testing business logic, not external APIs
- Use fixtures for common setup

### Test Patterns
```python
import pytest
from unittest.mock import Mock, patch

class TestMyPlugin:
    def test_generate_image_basic(self):
        # Test basic functionality
        pass
    
    @pytest.mark.parametrize("setting,expected", [
        ({"value": 1}, "result1"),
        ({"value": 2}, "result2"),
    ])
    def test_with_params(self, setting, expected):
        # Parameterized test
        pass
    
    @patch('requests.get')
    def test_with_mock(self, mock_get):
        # Test with mocked external dependencies
        mock_get.return_value.json.return_value = {"data": "test"}
        pass
```

## Web Frontend Conventions

### HTML/Templates
- Use Jinja2 templating
- Responsive design with Bootstrap
- Component-based structure
- Client-side JavaScript for interactivity

### CSS/JavaScript
- 2-space indentation for web files
- Bootstrap 5 for UI framework
- Font Awesome for icons
- Vanilla JavaScript (no frameworks currently)

## Hardware Abstraction

### Display Drivers
- Support multiple display types (Inky, Waveshare)
- Abstract display operations through `DisplayManager`
- Device-specific implementations in `src/display/`
- Mock display for development mode

## Security Considerations

- Validate all user inputs
- Sanitize external data
- No hardcoded credentials
- Use environment variables for API keys
- Rate limiting for external API calls

## Development Tips

### Common Pitfalls
1. **Display Hardware**: Always test with `--dev` flag first
2. **Plugin IDs**: Must match folder names and be unique
3. **Image Formats**: Ensure compatibility with e-ink displays (black/white/red)
4. **API Rate Limits**: Implement caching and rate limiting
5. **Time Zones**: Always use timezone-aware datetime objects

### Performance Considerations
- Cache expensive operations
- Optimize image generation for e-ink displays
- Use async operations where beneficial
- Consider display refresh patterns

## Getting Help

- Documentation: `docs/` directory
- Troubleshooting: `docs/troubleshooting.md`
- Plugin Development: `docs/building_plugins.md`
- Examples: Look at existing plugins for patterns

Remember: This project runs on resource-constrained hardware. Keep code efficient, images optimized, and dependencies minimal.