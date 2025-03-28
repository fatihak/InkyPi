import logging
import os
import json
from utils.app_utils import resolve_path, get_fonts
from utils.image_utils import take_screenshot_html
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
import base64

logger = logging.getLogger(__name__)

PLUGINS_DIR = resolve_path("plugins")
BASE_PLUGIN_DIR = os.path.join(PLUGINS_DIR, "base_plugin")

FRAME_STYLES = [
    {"name": "None", "icon": "frames/blank.png"},
    {"name": "Corner", "icon": "frames/corner.png"},
    {"name": "Top and Bottom", "icon": "frames/top_and_bottom.png"},
    {"name": "Rectangle", "icon": "frames/rectangle.png"},
]


class BasePlugin:
    """Base class for all plugins."""

    def __init__(self, config, **dependencies):
        self.config = config
        self.translations = {}
        self.current_language = config.get("language", "en")
        self._load_translations()

    def _load_translations(self):
        """Load translations for the plugin"""
        translations_dir = self.get_plugin_dir("translations")
        if not os.path.exists(translations_dir):
            return

        lang_file = os.path.join(translations_dir, f"{self.current_language}.json")
        fallback_file = os.path.join(translations_dir, "en.json")

        try:
            if os.path.exists(lang_file):
                with open(lang_file, "r", encoding="utf-8") as f:
                    self.translations = json.load(f)
            elif os.path.exists(fallback_file):
                with open(fallback_file, "r", encoding="utf-8") as f:
                    self.translations = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load translations: {e}")

    def translate(self, key, default=None):
        """Get translation for a key with fallback to default or key itself"""
        return self.translations.get(key, default or key)

    def generate_image(self, settings, device_config):
        raise NotImplementedError("generate_image must be implemented by subclasses")

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
            template_params["settings_template"] = (
                f"{self.get_plugin_id()}/settings.html"
            )

        template_params["frame_styles"] = FRAME_STYLES
        return template_params

    def read_file(self, file):
        return base64.b64encode(open(file, "rb").read()).decode("utf-8")

    def render_image(self, dimensions, html_file, css_file=None, template_params={}):
        # instantiate jinja2 env with base plugin and current plugin render directories
        base_render_dir = os.path.join(BASE_PLUGIN_DIR, "render")
        plugin_render_dir = self.get_plugin_dir("render")
        loader = FileSystemLoader([plugin_render_dir, base_render_dir])
        env = Environment(loader=loader, autoescape=select_autoescape(["html", "xml"]))

        # Add translation function to template environment
        env.globals["t"] = self.translate

        # load the base plugin and current plugin css files
        css_files = [os.path.join(base_render_dir, "plugin.css")]
        if css_file:
            plugin_css = os.path.join(plugin_render_dir, css_file)
            if Path(plugin_css).is_file():
                css_files.append(plugin_css)

        template_params["style_sheets"] = css_files
        template_params["width"] = dimensions[0]
        template_params["height"] = dimensions[1]
        template_params["font_faces"] = get_fonts()
        template_params["current_language"] = self.current_language

        # load and render the given html template
        template = env.get_template(html_file)
        rendered_html = template.render(template_params)

        return take_screenshot_html(rendered_html, dimensions)
