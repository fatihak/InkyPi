import os
from pathlib import Path

from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import resolve_path

WIDGETS_DIR = resolve_path("widgets")

class BaseWidget(BasePlugin):
    """Base class for all widgets."""
    def get_plugin_dir(self, path=None):
        plugin_dir = os.path.join(WIDGETS_DIR, self.get_plugin_id())
        if path:
            plugin_dir = os.path.join(plugin_dir, path)
        return plugin_dir

    def generate_settings_template(self):
        template_params = {"settings_template": "base_widget/settings.html"}

        settings_path = self.get_plugin_dir("settings.html")
        if Path(settings_path).is_file():
            template_params["settings_template"] = f"{self.get_plugin_id()}/settings.html"

        template_params['use_contrast_color'] = True
        return template_params