# Development Mode Enhancement Plan

## Overview
Add development-only functionality that serves HTML with live reload instead of rendering images, allowing rapid plugin development.

## Phase 1: Core HTML Serving Infrastructure

### 1. Add New Command Line Argument
- Extend `--dev` flag with `--serve-html` option in `inkypi.py:44`
- Add `SERVE_HTML_MODE = True` when enabled

### 2. Modify BasePlugin.render_image()
```python
# In base_plugin.py:83
def render_image(self, dimensions, html_file, css_file=None, template_params={}):
    # ... existing setup code ...
    
    template = self.env.get_template(html_file)
    rendered_html = template.render(template_params)
    
    if current_app.config.get('SERVE_HTML_MODE', False):
        # Return HTML content for development serving
        return {
            'html': rendered_html,
            'css_files': css_files,
            'template_params': template_params
        }
    else:
        # Current screenshot behavior
        return take_screenshot_html(rendered_html, dimensions)
```

### 3. Create Development Blueprint
- New file: `src/blueprints/dev.py`
- Add route `/dev/preview/<plugin_id>` for HTML serving
- Add route `/dev/preview/<plugin_id>/<instance_name>` for specific instances
- Store HTML content in memory or temporary files

## Phase 2: Live Reload Implementation

### 4. Add Dependencies
- `watchdog` - File system monitoring
- `flask-socketio` - WebSocket support for live reload

### 5. File Watching Service
```python
# New file: src/utils/file_watcher.py
class PluginFileWatcher:
    def __init__(self):
        self.observers = {}
        self.socketio = None
    
    def watch_plugin(self, plugin_id, plugin_dir):
        # Monitor HTML, CSS, and settings files
        # Emit WebSocket events on changes
```

### 6. WebSocket Integration
- Modify `inkypi.py` to initialize Flask-SocketIO
- Add client-side JavaScript for auto-reload
- Broadcast template changes to connected browsers

## Phase 3: Development UI Enhancements

### 7. Development Dashboard
- Extend main dashboard in development mode
- Show both HTML preview and screenshot side-by-side
- Add plugin selection for live preview

### 8. Plugin Preview Interface
```python
# In dev.py blueprint
@dev_bp.route('/dev/preview/<plugin_id>')
def plugin_preview(plugin_id):
    # Generate plugin HTML using existing settings
    # Return enhanced template with live reload script
    # Include dev tools panel
```

## Phase 4: Integration Points

### 9. Update Plugin Execution Flow
- Modify `refresh_task.py` to handle HTML mode
- Update `plugin.py:update_now` to serve HTML in dev mode
- Ensure playlist system works with HTML serving

### 10. Configuration Handling
- Extend development config (`device_dev.json`)
- Add HTML serving settings
- Configure file watching patterns

## Implementation Strategy

### Key Integration Points:
1. **BasePlugin.render_image()** - Core injection point for HTML vs image
2. **Flask app initialization** - Add SocketIO and dev blueprint
3. **Plugin execution** - Modify refresh task and manual updates
4. **File system** - Watch for template changes

### Development Workflow:
1. Start with `python inkypi.py --dev --serve-html`
2. Navigate to `http://localhost:8080/dev/preview/nhl_team_schedule`
3. Edit HTML/CSS files → automatic browser refresh
4. Changes to plugin settings → data refresh on page reload

### Security Considerations:
- HTML serving only in development mode
- Local-only access by default
- Input sanitization for preview mode

## Files to Modify/Create:
- `src/inkypi.py` - CLI args and Flask setup
- `src/plugins/base_plugin/base_plugin.py` - HTML vs image logic
- `src/blueprints/dev.py` - New development blueprint
- `src/utils/file_watcher.py` - File monitoring service
- `src/templates/dev_preview.html` - Development preview template
- `src/static/js/dev_reload.js` - Client-side live reload script
- `config/device_dev.json` - Development configuration

## Notes:
- Leverages existing Jinja2 template system and plugin architecture
- Clean separation between development and production modes
- Maintains all existing functionality when not in dev mode