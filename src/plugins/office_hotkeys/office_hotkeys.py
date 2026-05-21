import logging
import os

from plugins.base_plugin.base_plugin import BasePlugin

from . import constants, selection

logger = logging.getLogger(__name__)


class OfficeHotkeys(BasePlugin):
    """Renders a rotating Office keyboard-shortcut cheat sheet."""

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params["style_settings"] = True
        return template_params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        app = settings.get("app", "excel")
        level = settings.get("skillLevel", "intermediate")

        data_path = os.path.join(self.get_plugin_dir("data"), "shortcuts.json")
        shortcuts = selection.load_shortcuts(data_path)
        screen = selection.select_for_screen(shortcuts, app, level)
        if screen is None:
            raise RuntimeError(
                f"No shortcuts found for app='{app}' at level='{level}'"
            )

        theme = constants.APP_THEME[app]
        template_params = {
            "plugin_settings": settings,
            "app_label": theme["label"],
            "header_color": theme["color"],
            "category": screen["category"],
            "category_index": screen["category_index"],
            "category_count": screen["category_count"],
            "level_label": level.capitalize(),
            "hero": screen["hero"],
            "items": screen["list"],
            "pool_size": screen["pool_size"],
            "shown_count": 1 + len(screen["list"]),
        }
        return self.render_image(
            dimensions, "office_hotkeys.html", "office_hotkeys.css", template_params
        )
