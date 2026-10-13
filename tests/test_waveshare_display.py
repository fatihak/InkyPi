import os
import sys
import types

import pytest

# waveshare_display.py uses absolute imports rooted at src (e.g. "display.*"),
# so put src on the path to import it the same way the app does.
SRC_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from display.waveshare_display import WaveshareDisplay  # noqa: E402


class FakeDeviceConfig:
    """Minimal device_config stub for exercising WaveshareDisplay."""

    def __init__(self, display_type):
        self._values = {"display_type": display_type}

    def get_config(self, key, default=None):
        return self._values.get(key, default)

    def update_value(self, key, value, write=False):
        self._values[key] = value


class FakeEpd3in7:
    """Mimics the waveshare epd3in7 driver API (init(mode), Clear(color, mode),
    display_1Gray, no generic display())."""

    width = 280
    height = 480

    def __init__(self):
        self.calls = []

    def init(self, mode):
        self.calls.append(("init", mode))
        return 0

    def getbuffer(self, image):
        self.calls.append(("getbuffer", image))
        return b"buf"

    def display_1Gray(self, image):
        self.calls.append(("display_1Gray", image))

    def Clear(self, color, mode):
        self.calls.append(("Clear", color, mode))

    def sleep(self):
        self.calls.append(("sleep",))


class FakeMonoEpd:
    """Mimics a standard single-color driver (init(), Clear(), display(buf))."""

    width = 800
    height = 480

    def __init__(self):
        self.calls = []

    def init(self):
        self.calls.append(("init",))
        return 0

    def getbuffer(self, image):
        return b"buf"

    def display(self, buf):
        self.calls.append(("display", buf))

    def Clear(self):
        self.calls.append(("Clear",))

    def sleep(self):
        self.calls.append(("sleep",))


def _register_fake_driver(monkeypatch, display_type, epd_cls):
    module = types.ModuleType(f"display.waveshare_epd.{display_type}")
    module.EPD = epd_cls
    monkeypatch.setitem(sys.modules, f"display.waveshare_epd.{display_type}", module)


def test_epd3in7_init_passes_mode_argument(monkeypatch):
    _register_fake_driver(monkeypatch, "epd3in7", FakeEpd3in7)

    display = WaveshareDisplay(FakeDeviceConfig("epd3in7"))

    assert display.grayscale_mode_display is True
    assert display.bi_color_display is False
    # init() must be called with the required mode argument (regression for #525).
    assert display.epd_display.calls == [("init", 1)]
    # resolution should be derived from the driver dimensions (landscape).
    assert display.device_config.get_config("resolution") == [480, 280]


def test_epd3in7_display_uses_mode_specific_methods(monkeypatch):
    _register_fake_driver(monkeypatch, "epd3in7", FakeEpd3in7)

    display = WaveshareDisplay(FakeDeviceConfig("epd3in7"))
    display.epd_display.calls.clear()

    display.display_image(object())

    methods = [call[0] for call in display.epd_display.calls]
    assert methods == ["init", "Clear", "getbuffer", "display_1Gray", "sleep"]
    assert ("init", 1) in display.epd_display.calls
    assert ("Clear", 0xFF, 1) in display.epd_display.calls


def test_standard_mono_display_unaffected(monkeypatch):
    _register_fake_driver(monkeypatch, "epd7in5_V2", FakeMonoEpd)

    display = WaveshareDisplay(FakeDeviceConfig("epd7in5_V2"))

    assert display.grayscale_mode_display is False
    assert display.bi_color_display is False

    display.epd_display.calls.clear()
    display.display_image(object())

    methods = [call[0] for call in display.epd_display.calls]
    assert methods == ["init", "Clear", "display", "sleep"]
