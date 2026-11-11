import os
import sys
from unittest import mock

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils import eink  # noqa: E402

PALETTE = eink.SPECTRA6


def colours_of(image):
    rgb = np.asarray(image.convert("RGB")).reshape(-1, 3)
    return {tuple(int(v) for v in c) for c in np.unique(rgb, axis=0)}


def weather_like_image():
    """White background, black text, pastel blue/orange areas and an anti-aliased edge."""
    image = Image.new("RGB", (64, 48), (255, 255, 255))
    pixels = image.load()
    for x in range(64):
        for y in range(48):
            if y < 12:
                pixels[x, y] = (150, 190, 230)   # pastel blue
            elif y < 24:
                pixels[x, y] = (250, 190, 120)   # pastel orange
            elif y < 30:
                pixels[x, y] = (0, 0, 0)         # text
            elif y < 32:
                pixels[x, y] = (128, 128, 128)   # anti-aliasing
    return image


def test_resolve_mode():
    assert eink.resolve_mode("google_photos", {}) == eink.PHOTO
    assert eink.resolve_mode("weather", {}) == eink.GRAPHICS
    assert eink.resolve_mode("clock", {}) == eink.PHOTO
    assert eink.resolve_mode("weather", {"colourMode": "auto"}) == eink.GRAPHICS   # older settings
    assert eink.resolve_mode("weather", {"colourMode": "manual", "colourRendering": "photo"}) == eink.PHOTO
    assert eink.resolve_mode("weather", {"colourMode": "manual"}) == eink.GRAPHICS
    assert eink.resolve_mode("weather", {"colourMode": "photo"}) == eink.PHOTO
    assert eink.resolve_mode("image_folder", {"colourMode": "graphics"}) == eink.GRAPHICS
    assert eink.resolve_mode("weather", {"colourMode": "bogus"}) == eink.GRAPHICS
    assert eink.resolve_mode("weather", None) == eink.GRAPHICS


def _fake_driver(tmp_path, monkeypatch, source_line, name):
    """An Inky-like driver module whose set_image source can be inspected."""
    (tmp_path / f"{name}.py").write_text(
        f"DESATURATED_PALETTE = {PALETTE['pure'] + [[255, 255, 255]]}\n"
        f"SATURATED_PALETTE = {PALETTE['measured'] + [[255, 255, 255]]}\n"
        "class Inky:\n"
        "    def set_image(self, image, saturation=0.5):\n"
        f"        {source_line}\n"
        "            pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    module = __import__(name)
    return module.Inky()


def test_palette_from_inky_reads_the_driver(tmp_path, monkeypatch):
    driver = _fake_driver(tmp_path, monkeypatch, "if image.mode == 'P' and len(image.palette.colors) == 6:",
                          "fake_inky_spectra")
    palette = eink.palette_from_inky(driver)
    assert palette == {"pure": PALETTE["pure"], "measured": PALETTE["measured"]}


def test_palette_from_inky_without_pure_colour_path(tmp_path, monkeypatch):
    assert eink.palette_from_inky(_fake_driver(tmp_path, monkeypatch, "if True:", "fake_inky_other")) is None
    assert eink.palette_from_inky(object()) is None


def test_graphics_mode_uses_only_pure_ink_colours_and_crisp_black_and_white():
    image = weather_like_image()
    indices = eink.render_indices(image, PALETTE, eink.GRAPHICS)
    out = eink.to_pure_palette_image(indices, PALETTE)
    assert out.mode == "P" and len(out.palette.colors) <= 6
    assert colours_of(out) <= {tuple(c) for c in PALETTE["pure"]}
    rgb = np.asarray(out.convert("RGB"))
    assert (rgb[24:30] == 0).all()                       # text stays solid black
    assert (rgb[40:] == 255).all()                       # paper stays white
    blue = rgb[:12].reshape(-1, 3)
    # the pastel blue is rendered with a fair amount of blue ink, not a few sparse dots
    assert (blue == [0, 0, 255]).all(axis=1).mean() > 0.25


def test_graphics_mode_renders_greys_with_black_and_white_only():
    gradient = Image.linear_gradient("L").resize((64, 64)).convert("RGB")
    out = eink.to_pure_palette_image(eink.render_indices(gradient, PALETTE, eink.GRAPHICS), PALETTE)
    assert colours_of(out) <= {(0, 0, 0), (255, 255, 255)}


def test_photo_mode_matches_driver_style_dithering():
    image = weather_like_image()
    indices = eink.render_indices(image, PALETTE, eink.PHOTO)
    assert indices.shape == (48, 64) and indices.max() < 6


def test_adapt_colours_leaves_neutral_pixels():
    image = Image.new("RGB", (4, 1))
    image.putdata([(0, 0, 0), (255, 255, 255), (128, 128, 128), (150, 190, 230)])
    adapted = eink.adapt_colours(image, PALETTE)
    out = [adapted.getpixel((x, 0)) for x in range(4)]
    assert out[:3] == [(0, 0, 0), (255, 255, 255), (128, 128, 128)]
    r, g, b = out[3]
    assert b > r and sum(out[3]) < 150 + 190 + 230   # more saturated and darker


def test_simulate_shows_measured_inks():
    sim = eink.simulate(weather_like_image(), PALETTE, eink.GRAPHICS)
    assert sim.size == (64, 48) and sim.getpixel((0, 47)) == (255, 255, 255)
    assert sim.getpixel((0, 26)) == (0, 0, 0)


def test_colour_plan_global_and_manual():
    global_settings = {"saturation": 1.4, "contrast": 1.2, "inky_saturation": 0.6}
    plan = eink.colour_plan("weather", {"colourSaturation": "0.1"}, global_settings)
    assert plan == {"mode": eink.GRAPHICS, "enhance": global_settings, "saturation": 0.6, "manual": False}

    plan = eink.colour_plan("google_photos", {
        "colourMode": "manual", "colourRendering": "graphics", "colourSaturation": "1.8",
        "colourContrast": "9", "colourBrightness": "oops", "colourInk": "0.2"}, global_settings)
    assert plan["mode"] == eink.GRAPHICS and plan["manual"] and plan["saturation"] == 0.2
    assert plan["enhance"]["saturation"] == 1.8
    assert plan["enhance"]["contrast"] == 2.0          # clamped
    assert plan["enhance"]["brightness"] == 1.0        # invalid -> global value (default 1.0)
    assert global_settings["saturation"] == 1.4        # global settings untouched
    assert eink.colour_plan("clock", None, None)["enhance"] == {}


def test_display_manager_prepare_colours():
    from display.display_manager import DisplayManager
    manager = DisplayManager.__new__(DisplayManager)
    manager.display = mock.Mock()
    manager.display.get_palette.return_value = PALETTE
    manager.device_config = mock.Mock()
    manager.device_config.get_config.return_value = {"inky_saturation": 0.5}
    image = weather_like_image()
    photo = eink.colour_plan("image_folder", {}, {})
    graphics = eink.colour_plan("weather", {}, {})
    manual_photo = eink.colour_plan("image_folder", {"colourMode": "manual", "colourInk": "0.9"}, {})
    assert manager.prepare_colours(image, None) is image
    assert manager.prepare_colours(image, photo) is image             # the driver dithers photos itself
    for plan in (graphics, manual_photo):                              # own ink saturation: rendered here
        out = manager.prepare_colours(image, plan)
        assert out.mode == "P" and len(out.palette.colors) <= 6

    manager.display.get_palette.return_value = None   # other displays: unchanged
    assert manager.prepare_colours(image, graphics) is image
