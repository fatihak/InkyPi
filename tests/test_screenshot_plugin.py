import sys
from pathlib import Path

import pytest
from PIL import Image

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import plugins.screenshot.screenshot as screenshot_module
from plugins.screenshot.screenshot import Screenshot


class FakeDeviceConfig:
    def get_resolution(self):
        return (300, 200)

    def get_config(self, key, default=None):
        if key == "orientation":
            return "horizontal"
        return default


def test_screenshot_passes_render_wait_to_chromium(monkeypatch):
    call = {}

    def fake_take_screenshot(target, dimensions, timeout_ms=None, virtual_time_budget_ms=None):
        call["target"] = target
        call["dimensions"] = dimensions
        call["timeout_ms"] = timeout_ms
        call["virtual_time_budget_ms"] = virtual_time_budget_ms
        return Image.new("RGB", dimensions, "white")

    monkeypatch.setattr(screenshot_module, "take_screenshot", fake_take_screenshot)

    plugin = Screenshot({"id": "screenshot"})
    image = plugin.generate_image(
        {"url": "https://example.com", "renderWaitMs": "2500"},
        FakeDeviceConfig(),
    )

    assert image.size == (300, 200)
    assert call == {
        "target": "https://example.com",
        "dimensions": (300, 200),
        "timeout_ms": 40000,
        "virtual_time_budget_ms": 2500,
    }


def test_screenshot_skips_if_blank(monkeypatch):
    def fake_take_screenshot(target, dimensions, timeout_ms=None, virtual_time_budget_ms=None):
        return Image.new("RGB", dimensions, "white")

    monkeypatch.setattr(screenshot_module, "take_screenshot", fake_take_screenshot)

    plugin = Screenshot({"id": "screenshot"})
    settings = {"url": "https://example.com", "skipIfBlank": "true"}
    
    skip_reason = plugin.skip_display_condition(settings, FakeDeviceConfig(), None)
    assert skip_reason == "Screenshot is blank"


def test_screenshot_does_not_skip_if_not_blank(monkeypatch):
    def fake_take_screenshot(target, dimensions, timeout_ms=None, virtual_time_budget_ms=None):
        img = Image.new("RGB", dimensions, "white")
        img.putpixel((0, 0), (0, 0, 0))
        return img

    monkeypatch.setattr(screenshot_module, "take_screenshot", fake_take_screenshot)

    plugin = Screenshot({"id": "screenshot"})
    settings = {"url": "https://example.com", "skipIfBlank": "true"}
    
    skip_reason = plugin.skip_display_condition(settings, FakeDeviceConfig(), None)
    assert skip_reason is None


def test_screenshot_caches_image_between_skip_and_generate(monkeypatch):
    call_count = 0

    def fake_take_screenshot(target, dimensions, timeout_ms=None, virtual_time_budget_ms=None):
        nonlocal call_count
        call_count += 1
        img = Image.new("RGB", dimensions, "white")
        img.putpixel((0, 0), (0, 0, 0))
        return img

    monkeypatch.setattr(screenshot_module, "take_screenshot", fake_take_screenshot)

    plugin = Screenshot({"id": "screenshot"})
    settings = {"url": "https://example.com", "skipIfBlank": "true"}
    device_config = FakeDeviceConfig()

    # First call to skip_display_condition should capture
    skip_reason = plugin.skip_display_condition(settings, device_config, None)
    assert skip_reason is None
    assert call_count == 1

    # Second call to generate_image should use cache
    image = plugin.generate_image(settings, device_config)
    assert image is not None
    assert call_count == 1


def test_screenshot_rejects_invalid_render_wait():
    plugin = Screenshot({"id": "screenshot"})

    with pytest.raises(RuntimeError, match="whole number"):
        plugin.generate_image(
            {"url": "https://example.com", "renderWaitMs": "later"},
            FakeDeviceConfig(),
        )
