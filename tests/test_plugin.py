"""Unittest for the plugins."""

import json
import unittest
from pathlib import Path
from unittest import mock

from loguru import logger
from PIL import Image

from inkypi.plugins.plugin_registry import get_plugin_instance, load_plugins
from inkypi.utils.image_utils import change_orientation, resize_image


class TestPlugin(unittest.TestCase):
    """Unittest for the plugins."""

    def setUp(self) -> None:
        """Setup for testing the plugin."""
        base_path = Path(__file__).parents[1]

        self.plugin_config_file = base_path / "install/config_base/plugins.json"
        self.resolutions = [
            [400, 300],  # Inky wHAT
            [640, 400],  # Inky Impression 4"
            [600, 448],  # Inky Impression 5.7"
            [800, 480],  # Inky Impression 7.3"
        ]
        self.orientations = ["horizontal", "vertical"]

    def load_plugin_config(self, plugin_id: str) -> None | list[dict[str, str]]:
        """Load the config dict for the given plugin id.

        Parameters
        ----------
        plugin_id : str
            ID of the plugin.

        Returns
        -------
        dict[str, str] | None
            Config dict for the plugin. None if the plugin could not be resolved.

        """
        with self.plugin_config_file.open(encoding="UTF-8") as f:
            plugins = json.load(f)
        plugin_config = [config for config in plugins if config.get("id") == plugin_id]
        if not plugin_config:
            return None
        if len(plugin_config) > 1:
            logger.warning(
                f"Found multiple configs matching {plugin_id}. Selecting first match."
            )
        load_plugins(plugin_config)
        return plugin_config[0]

    def test_ai_test(self) -> None:
        """Test if the ai-plugin works."""
        plugin_id = "ai_text"

        plugin_settings = {
            "title": "Today In History",
            "textModel": "gpt-4o",
            "textPrompt": "idk",
            "selectedFrame": "Rectangle",
        }
        plugin_config = self.load_plugin_config(plugin_id)
        if plugin_config is None:
            raise unittest.SkipTest(
                f"Plugin {plugin_id} not found in plugin config file: {self.plugin_config_file}"
            )
        plugin_instance = get_plugin_instance(plugin_config)

        total_height = sum([max(resolution) for resolution in self.resolutions])
        total_width = max([max(resolution) for resolution in self.resolutions]) * 2

        composite = Image.new("RGB", (total_width, total_height), color="gray")
        y = 0
        mock_device_config = mock.MagicMock()
        for resolution in self.resolutions:
            x = 0
            width, height = resolution
            for orientation in self.orientations:
                mock_device_config.get_resolution.return_value = resolution
                mock_device_config.get_config.return_value = orientation

                img = plugin_instance.generate_image(
                    plugin_settings, mock_device_config
                )

                # post processing thats applied before being displayed
                img = change_orientation(img, orientation)
                img = resize_image(
                    img, resolution, plugin_config.get("image_settings", [])
                )
                # rotate the image again when pasting
                if orientation == "vertical":
                    img = img.rotate(-90, expand=1)
                composite.paste(img, (x, y))
                x = int(total_width / 2)
            y += max(width, height)

        composite.show()
