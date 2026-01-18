import json
import pytest
from unittest.mock import patch, MagicMock
from PIL import Image
from plugins.plugin_registry import load_plugins, get_plugin_instance
from utils.image_utils import resize_image, change_orientation

PLUGIN_CONFIG_FILE = "../src/plugins/plugins.json"
RESOLUTIONS = [
    [400, 300],  # Inky wHAT
    [640, 400],  # Inky Impression 4"
    [600, 448],  # Inky Impression 5.7"
    [800, 480],  # Inky Impression 7.3"
]
ORIENTATIONS = ["horizontal", "vertical"]

plugin_id = "daily_art"
plugin_settings = {
    "title": "Today In History",
    "textModel": "gpt-4o",
    "textPrompt": "idk",
    "selectedFrame": "Rectangle",
}


@pytest.fixture
def mock_device_config():
    return MagicMock()


@pytest.fixture
def plugin_config():
    with open(PLUGIN_CONFIG_FILE) as f:
        plugins = json.load(f)
    config = [config for config in plugins if config.get("id") == plugin_id]
    if not config:
        pytest.fail(
            f"Plugin {plugin_id} not found in plugin config file: {PLUGIN_CONFIG_FILE}"
        )
    return config[0]


@pytest.fixture
def plugin_instance(plugin_config):
    load_plugins([plugin_config])
    return get_plugin_instance(plugin_config)


def test_generate_composite_image(mock_device_config, plugin_instance, plugin_config):
    total_height = sum([max(resolution) for resolution in RESOLUTIONS])
    total_width = max([max(resolution) for resolution in RESOLUTIONS]) * 2
    composite = Image.new("RGB", (total_width, total_height), color="gray")

    y = 0
    for resolution in RESOLUTIONS:
        x = 0
        width, height = resolution
        for orientation in ORIENTATIONS:
            mock_device_config.get_resolution.return_value = resolution
            mock_device_config.get_config.return_value = orientation

            img = plugin_instance.generate_image(plugin_settings, mock_device_config)
            assert img is not None, "Generated image should not be None"
            assert isinstance(img, Image.Image), "Generated image should be a PIL Image"

            img = change_orientation(img, orientation)
            img = resize_image(img, resolution, plugin_config.get("image_settings", []))

            if orientation == "vertical":
                img = img.rotate(-90, expand=1)

            composite.paste(img, (x, y))
            x = int(total_width / 2)
        y += max(width, height)

    composite.show()
    assert composite is not None, "Final composite image should not be None"
