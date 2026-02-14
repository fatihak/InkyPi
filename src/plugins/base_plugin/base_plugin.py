import logging
import os
from utils.app_utils import resolve_path, get_fonts
from utils.image_utils import take_screenshot_html
from utils.image_loader import AdaptiveImageLoader
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
import asyncio
import base64
from datetime import datetime
import pytz
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

STATIC_DIR = resolve_path("static")
PLUGINS_DIR = resolve_path("plugins")
BASE_PLUGIN_DIR =  os.path.join(PLUGINS_DIR, "base_plugin")
BASE_PLUGIN_RENDER_DIR = os.path.join(BASE_PLUGIN_DIR, "render")

FRAME_STYLES = [
    {
        "name": "None",
        "icon": "frames/blank.png"
    },
    {
        "name": "Corner",
        "icon": "frames/corner.png"
    },
    {
        "name": "Top and Bottom",
        "icon": "frames/top_and_bottom.png"
    },
    {
        "name": "Rectangle",
        "icon": "frames/rectangle.png"
    }
]

class BasePlugin:
    """Base class for all plugins."""
    def __init__(self, config, **dependencies):
        self.config = config

        # Initialize adaptive image loader for device-aware image processing
        self.image_loader = AdaptiveImageLoader()

        self.render_dir = self.get_plugin_dir("render")
        if os.path.exists(self.render_dir):
            # instantiate jinja2 env with base plugin and current plugin render directories
            loader = FileSystemLoader([self.render_dir, BASE_PLUGIN_RENDER_DIR])
            self.env = Environment(
                loader=loader,
                autoescape=select_autoescape(['html', 'xml'])
            )

    def generate_image(self, settings, device_config):
        raise NotImplementedError("generate_image must be implemented by subclasses")

    def cleanup(self, settings):
        """Optional cleanup method that plugins can override to delete associated resources.

        Called when a plugin instance is deleted. Plugins should override this to clean up
        any files, external resources, or other data associated with the plugin instance.

        Args:
            settings: The plugin instance's settings dict, which may contain file paths or other resources
        """
        pass  # Default implementation does nothing

    def get_plugin_id(self):
        return self.config.get("id")

    def get_plugin_dir(self, path=None):
        plugin_dir = os.path.join(PLUGINS_DIR, self.get_plugin_id())
        if path:
            plugin_dir = os.path.join(plugin_dir, path)
        return plugin_dir

    def generate_settings_template(self):
        template_params = {"settings_template": "base_plugin/settings.html"}

        settings_path = self.get_plugin_dir("settings.html")
        if Path(settings_path).is_file():
            template_params["settings_template"] = f"{self.get_plugin_id()}/settings.html"

        template_params['frame_styles'] = FRAME_STYLES
        return template_params

    def render_image(self, dimensions, html_file, css_file=None, template_params={}, device_config=None):
        # load the base plugin and current plugin css files
        css_files = [os.path.join(BASE_PLUGIN_RENDER_DIR, "plugin.css")]
        if css_file:
            plugin_css = os.path.join(self.render_dir, css_file)
            css_files.append(plugin_css)

        template_params["style_sheets"] = css_files
        template_params["width"] = dimensions[0]
        template_params["height"] = dimensions[1]
        template_params["font_faces"] = get_fonts()
        template_params["static_dir"] = STATIC_DIR

        # Add debug info if enabled
        if self._should_show_debug_info(template_params.get('plugin_settings', {}), device_config):
            template_params['debug_info'] = self._get_debug_info(template_params.get('plugin_settings', {}), device_config)

        # load and render the given html template
        template = self.env.get_template(html_file)
        rendered_html = template.render(template_params)

        return take_screenshot_html(rendered_html, dimensions)

    def add_debug_overlay(self, image, settings, device_config):
        """Add debug overlay to any PIL Image (for image-based plugins).

        This method allows image-based plugins (that don't use render_image)
        to add debug information by calling this method before returning.

        Args:
            image: PIL Image to add debug overlay to
            settings: Plugin settings dict
            device_config: Device configuration object

        Returns:
            PIL Image with debug overlay (if debug mode is enabled)
        """
        from PIL import ImageDraw, ImageFont

        # Check if debug info should be shown
        if not self._should_show_debug_info(settings, device_config):
            return image

        # Get debug info
        debug_info = self._get_debug_info(settings, device_config)

        # Convert image to RGB if needed (for drawing)
        if image.mode != 'RGB':
            img_with_debug = image.convert('RGB')
        else:
            img_with_debug = image.copy()

        draw = ImageDraw.Draw(img_with_debug)

        # Try to load a nice font, fall back to default
        try:
            font_size = max(14, int(min(image.width, image.height) * 0.035))
            font = ImageFont.truetype(os.path.join(STATIC_DIR, "fonts/Jost.ttf"), font_size)
            small_font = ImageFont.truetype(os.path.join(STATIC_DIR, "fonts/Jost.ttf"), int(font_size * 0.85))
        except:
            font = ImageFont.load_default()
            small_font = font

        # Build debug text as label-value pairs (no emoji for PIL - standard fonts don't support it)
        title = f"DEBUG: {debug_info.get('plugin_id', 'unknown')}"
        data_rows = []  # List of (label, value) tuples

        if debug_info.get('image_generated'):
            data_rows.append(("Last Refresh:", debug_info['image_generated']))
        if debug_info.get('refresh_interval'):
            data_rows.append(("Interval:", debug_info['refresh_interval']))

        # Add custom debug info
        has_divider = False
        if debug_info.get('custom'):
            has_divider = True
            for key, value in debug_info['custom'].items():
                label = key.replace('_', ' ').title()
                data_rows.append((f"{label}:", str(value)))

        # Calculate column widths
        padding = 12
        line_height = font_size + 5

        # Find max label width
        max_label_width = max([draw.textlength(label, font=small_font) for label, _ in data_rows], default=0)

        # Find max value width
        max_value_width = max([draw.textlength(value, font=small_font) for _, value in data_rows], default=0)

        # Calculate total width (label + gap + value + padding)
        gap = 20
        title_width = draw.textlength(title, font=font)
        content_width = max_label_width + gap + max_value_width
        max_width = max(title_width, content_width) + padding * 2

        # Calculate height
        num_lines = 1 + len(data_rows) + (1 if has_divider else 0)  # title + data rows + divider
        box_height = num_lines * line_height + padding * 2

        # Position in top-right corner
        box_x = image.width - max_width - 8
        box_y = 8

        # Draw solid white background with black border
        draw.rectangle(
            [box_x, box_y, box_x + max_width, box_y + box_height],
            fill=(255, 255, 255),  # Solid white background
            outline=(0, 0, 0),      # Black border
            width=2
        )

        # Draw title
        y = box_y + padding
        draw.text((box_x + padding, y), title, fill=(0, 0, 0), font=font)
        y += line_height

        # Draw data rows with two-column layout
        label_x = box_x + padding
        value_x = box_x + max_width - padding  # Right-align values

        divider_drawn = False
        for i, (label, value) in enumerate(data_rows):
            # Draw divider before custom fields
            if has_divider and not divider_drawn and debug_info.get('custom'):
                # Check if this is the first custom field
                standard_fields = 5  # Image, Display, Status, Gen, Int
                current_standard = min(i, standard_fields)
                if i >= len(data_rows) - len(debug_info['custom']):
                    y_divider = y + line_height // 4
                    draw.line(
                        [(box_x + padding, y_divider),
                         (box_x + max_width - padding, y_divider)],
                        fill=(0, 0, 0),
                        width=1
                    )
                    y += line_height
                    divider_drawn = True

            # Draw label (left-aligned)
            draw.text((label_x, y), label, fill=(0, 0, 0), font=small_font)

            # Draw value (right-aligned)
            value_width = draw.textlength(value, font=small_font)
            draw.text((value_x - value_width, y), value, fill=(0, 0, 0), font=small_font)

            y += line_height

        return img_with_debug

    def _should_show_debug_info(self, plugin_settings, device_config):
        """Determine if debug info should be displayed.

        Priority:
        1. Plugin-level setting (displayRefreshTime)
        2. Device-level debug mode setting
        """
        # Check plugin-level override first
        if 'displayRefreshTime' in plugin_settings:
            return plugin_settings.get('displayRefreshTime') == 'true'

        # Check device-level setting
        if device_config:
            return device_config.get_config('show_debug_info', default=False)

        return False

    def _get_debug_info(self, plugin_settings, device_config):
        """Generate debug information for display.

        This base implementation provides:
        - Plugin ID
        - Last refresh timestamp (when image was generated)
        - Refresh interval

        Plugins can override get_custom_debug_info() to add specialized debug data.
        """
        debug_info = {}

        # Get timezone and time format from device config
        tz = pytz.timezone(device_config.get_config('timezone', default='America/New_York')) if device_config else pytz.UTC
        time_format = device_config.get_config('time_format', default='12h') if device_config else '12h'

        # Plugin identification (just ID, not name)
        debug_info['plugin_id'] = self.get_plugin_id()

        # Image generation timestamp (current time)
        now = datetime.now(tz)
        if time_format == '24h':
            debug_info['image_generated'] = now.strftime("%Y-%m-%d %H:%M:%S")
        else:
            debug_info['image_generated'] = now.strftime("%Y-%m-%d %I:%M:%S %p")

        # Refresh interval (from device config)
        if device_config:
            interval_seconds = device_config.get_config('plugin_cycle_interval_seconds', default=3600)
            if interval_seconds >= 3600:
                hours = interval_seconds / 3600
                debug_info['refresh_interval'] = f"{hours:.1f}h" if hours != int(hours) else f"{int(hours)}h"
            elif interval_seconds >= 60:
                minutes = interval_seconds / 60
                debug_info['refresh_interval'] = f"{minutes:.1f}m" if minutes != int(minutes) else f"{int(minutes)}m"
            else:
                debug_info['refresh_interval'] = f"{interval_seconds}s"

        # Add custom debug info from plugin
        custom_info = self.get_custom_debug_info(plugin_settings, device_config)
        if custom_info:
            debug_info['custom'] = custom_info

        return debug_info

    def get_custom_debug_info(self, plugin_settings, device_config):
        """Override this method in plugins to add specialized debug information.

        Returns:
            dict: Custom debug fields to display, or None if no custom info

        Example:
            return {
                'api_provider': 'OpenWeatherMap',
                'last_api_call': '2024-01-01 12:00:00',
                'cache_status': 'hit',
                'data_age': '5 minutes'
            }
        """
        return None
