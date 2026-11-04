import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import layout_manager
from layout_manager import (
    Region, ResolutionOverride, compose, compute_pip_region, get_canvas_size,
    parse_instance_ref, render_plugin_instance,
)


class FakeDeviceConfig:
    def __init__(self, resolution=(800, 480), orientation="horizontal", instances=None, plugins=None):
        self.resolution = resolution
        self.orientation = orientation
        self.instances = instances or {}
        self.plugins = plugins or {}
        self.plugin_image_dir = "/tmp"

    def get_resolution(self):
        return self.resolution

    def get_config(self, key=None, default=None):
        return {"orientation": self.orientation}.get(key, default)

    def get_playlist_manager(self):
        return self

    def find_plugin(self, plugin_id, name):
        return self.instances.get((plugin_id, name))

    def get_plugin(self, plugin_id):
        return self.plugins.get(plugin_id)


class FakeInstance:
    def __init__(self, settings):
        self.settings = settings


class SolidPlugin:
    """Renders a solid colour at whatever resolution the device config reports."""
    def __init__(self, config):
        self.config = config
        self.calls = []

    def generate_image(self, settings, device_config):
        dims = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dims = dims[::-1]
        self.calls.append(dims)
        return Image.new("RGB", dims, settings["color"])


class TestComputePipRegion:

    @pytest.mark.parametrize(
        "corner,expected",
        [
            ("top-left", Region(10, 10, 200, 120)),
            ("top-right", Region(590, 10, 200, 120)),
            ("bottom-left", Region(10, 350, 200, 120)),
            ("bottom-right", Region(590, 350, 200, 120)),
        ],
    )
    def test_corners(self, corner, expected):
        assert compute_pip_region((800, 480), corner, 25, margin=10) == expected

    def test_full_size_ignores_margin(self):
        assert compute_pip_region((800, 480), "bottom-right", 100, margin=20) == Region(0, 0, 800, 480)

    def test_size_is_clamped(self):
        assert compute_pip_region((800, 480), "top-left", 250).size == (800, 480)
        assert compute_pip_region((800, 480), "top-left", 0).size == (8, 5)

    def test_invalid_corner(self):
        with pytest.raises(ValueError):
            compute_pip_region((800, 480), "middle", 25)


class TestResolutionOverride:

    def test_horizontal(self):
        config = ResolutionOverride(FakeDeviceConfig(), (200, 120))
        assert config.get_resolution() == (200, 120)
        assert config.plugin_image_dir == "/tmp"

    def test_vertical_is_stored_pre_rotation(self):
        device_config = FakeDeviceConfig(orientation="vertical")
        assert get_canvas_size(device_config) == (480, 800)
        config = ResolutionOverride(device_config, (120, 200))
        # plugins flip the resolution for vertical displays, landing on the region size
        assert config.get_resolution()[::-1] == (120, 200)


class TestRenderAndCompose:

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        self.plugin = SolidPlugin({"id": "solid"})
        monkeypatch.setattr(layout_manager, "get_plugin_instance", lambda config: self.plugin)
        self.device_config = FakeDeviceConfig(
            instances={("solid", "Red"): FakeInstance({"color": "red"}),
                       ("solid", "Blue"): FakeInstance({"color": "blue"})},
            plugins={"solid": {"id": "solid"}},
        )

    def test_parse_instance_ref(self):
        assert parse_instance_ref("weather/Home Weather") == ("weather", "Home Weather")
        with pytest.raises(RuntimeError):
            parse_instance_ref("")

    def test_renders_at_region_size(self):
        image = render_plugin_instance(self.device_config, "solid/Red", (200, 120))
        assert image.size == (200, 120)
        assert self.plugin.calls == [(200, 120)]

    def test_renders_large_and_scales_down(self):
        image = render_plugin_instance(self.device_config, "solid/Red", (200, 120), render_size=(800, 480))
        assert image.size == (200, 120)
        assert self.plugin.calls == [(800, 480)]

    def test_missing_instance(self):
        with pytest.raises(RuntimeError, match="no longer exists"):
            render_plugin_instance(self.device_config, "solid/Green", (200, 120))

    def test_compose_places_overlay_with_border(self):
        region = compute_pip_region((800, 480), "bottom-right", 25, margin=10)
        background = render_plugin_instance(self.device_config, "solid/Red", (800, 480))
        overlay = render_plugin_instance(self.device_config, "solid/Blue", region.size)

        canvas = compose((800, 480), [(background, Region(0, 0, 800, 480)), (overlay, region)], border_width=2)

        assert canvas.size == (800, 480)
        assert canvas.getpixel((10, 10)) == (255, 0, 0)
        assert canvas.getpixel((region.x + 50, region.y + 50)) == (0, 0, 255)
        assert canvas.getpixel((region.x, region.y)) == (0, 0, 0)
        assert canvas.getpixel((789, 469)) == (0, 0, 0)
        assert canvas.getpixel((795, 475)) == (255, 0, 0)
