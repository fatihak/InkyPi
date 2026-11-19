import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils import text_font  # noqa: E402
from utils.app_utils import get_font  # noqa: E402


@pytest.fixture(autouse=True)
def restore_state():
    saved = dict(text_font._state)
    yield
    text_font._state.update(saved)


def test_defaults_and_unknown_values():
    text_font.configure("bogus", "bogus", "inky")
    assert text_font.current() == text_font.DEFAULT == "dejavu"
    assert text_font.rendering() == text_font.CRISP


def test_auto_rendering_depends_on_the_display():
    text_font.configure("dejavu", "auto", "inky")
    assert text_font.rendering() == text_font.CRISP
    text_font.configure(display_type="epd7in5_V2")
    assert text_font.rendering() == text_font.CRISP
    text_font.configure(display_type="mock")
    assert text_font.rendering() == text_font.SMOOTH
    text_font.configure(rendering="crisp")
    assert text_font.rendering() == text_font.CRISP


def test_configure_from_device_config():
    config = mock.Mock()
    config.get_config.side_effect = lambda key, default=None: {
        "text_font": "inter", "text_rendering": "smooth", "display_type": "inky"}.get(key, default)
    text_font.configure_from(config)
    assert (text_font.current(), text_font.rendering()) == ("inter", text_font.SMOOTH)


def test_original_jost_smooth_keeps_the_previous_rendering():
    text_font.configure("jost", "smooth", "inky")
    assert not text_font.overrides_template_font()
    assert text_font.browser_env() is None
    text_font.configure("jost", "crisp")
    assert text_font.overrides_template_font()


def test_fontconfig_maps_jost_to_the_chosen_font():
    crisp = text_font.fontconfig_xml("dejavu", text_font.CRISP)
    assert "<string>Jost</string>" in crisp and "<string>DejaVu Sans</string>" in crisp
    assert "<edit name=\"antialias\" mode=\"assign\"><bool>false</bool>" in crisp
    assert "hintfull" in crisp
    smooth = text_font.fontconfig_xml("inter", text_font.SMOOTH)
    assert "<edit name=\"antialias\" mode=\"assign\"><bool>true</bool>" in smooth
    jost = text_font.fontconfig_xml("jost", text_font.CRISP)
    assert 'binding="strong"' not in jost   # no alias needed


def test_browser_env_writes_the_fontconfig_file(tmp_path, monkeypatch):
    monkeypatch.setattr(text_font.tempfile, "gettempdir", lambda: str(tmp_path))
    text_font.configure("liberation", "crisp", "inky")
    env = text_font.browser_env()
    path = env["FONTCONFIG_FILE"]
    assert path.startswith(str(tmp_path)) and "Liberation Sans" in open(path).read()
    assert text_font.browser_env()["FONTCONFIG_FILE"] == path   # reused


def test_bundled_font_files_exist():
    for font in text_font.FONTS.values():
        for name in font["files"].values():
            assert os.path.isfile(os.path.join(text_font.FONT_DIR, name)), name


def test_pillow_text_uses_the_chosen_font():
    text_font.configure("dejavu", "crisp", "inky")
    assert get_font("Jost", 20).getname()[0] == "DejaVu Sans"
    assert get_font("Jost", 20, "bold").getname()[1] == "Bold"
    text_font.configure("jost")
    assert get_font("Jost", 20).getname()[0] == "Jost"
    text_font.configure("inter")
    assert get_font("Jost", 20).getname()[0] == "Inter"
