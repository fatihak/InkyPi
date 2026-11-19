"""Font and rendering of the text in plugin renders.

Plugin templates write their text in the "Jost" family (HTML, CSS and Chart.js canvases),
and a few plugins draw captions with Pillow using the same family.

Two settings:

- the font: Jost (the original thin geometric font) or a font that stays regular at small
  sizes on a coarse pixel grid (DejaVu Sans, Liberation Sans, Inter, Lexend);
- the rendering:
    crisp:  monochrome text with full hinting - every stem is snapped to whole pixels, so
            the text is already pure black and white. Best for colour, black and white and
            black/white/red panels, which only show full pixels: anti-aliased text would be
            thresholded or dithered into uneven or dotted letters.
    smooth: grey anti-aliasing, for panels or screens that show shades of grey.
    auto:   smooth on the development (mock) display, crisp on e-paper panels.

Both are applied with a fontconfig file given to the headless browser, which also maps the
"Jost" family to the chosen font, so no plugin needs to change.
"""

import logging
import os
import tempfile
from xml.sax.saxutils import escape

from utils.app_utils import resolve_path

logger = logging.getLogger(__name__)

FONT_DIR = resolve_path(os.path.join("static", "fonts", "text"))
JOST_DIR = resolve_path(os.path.join("static", "fonts"))
TEMPLATE_FAMILY = "Jost"

DEFAULT = "dejavu"
JOST = "jost"
FONTS = {
    # bytecode-hinted fonts: their own instructions place stems on the pixel grid
    "dejavu": {"label": "DejaVu Sans", "family": "DejaVu Sans", "autohint": False,
               "files": {"normal": "DejaVuSans.ttf", "bold": "DejaVuSans-Bold.ttf"}},
    "liberation": {"label": "Liberation Sans", "family": "Liberation Sans", "autohint": False,
                   "files": {"normal": "LiberationSans-Regular.ttf", "bold": "LiberationSans-Bold.ttf"}},
    # unhinted fonts: FreeType's auto-hinter snaps them
    "inter": {"label": "Inter", "family": "Inter", "autohint": True,
              "files": {"normal": "Inter.ttf"}},
    "lexend": {"label": "Lexend", "family": "Lexend", "autohint": True,
               "files": {"normal": "Lexend.ttf"}},
    JOST: {"label": "Jost", "family": TEMPLATE_FAMILY, "autohint": True, "files": {}},
}

AUTO, CRISP, SMOOTH = "auto", "crisp", "smooth"
RENDERINGS = (AUTO, CRISP, SMOOTH)
SMOOTH_DISPLAYS = {"mock"}  # screens with shades of grey (development display)

_state = {"font": DEFAULT, "rendering": AUTO, "display_type": "inky"}


def configure(font=None, rendering=None, display_type=None):
    """Sets the text font and rendering (unknown values fall back to the defaults)."""
    if font is not None:
        _state["font"] = font if font in FONTS else DEFAULT
    if rendering is not None:
        _state["rendering"] = rendering if rendering in RENDERINGS else AUTO
    if display_type is not None:
        _state["display_type"] = display_type


def configure_from(device_config):
    configure(device_config.get_config("text_font", default=DEFAULT),
              device_config.get_config("text_rendering", default=AUTO),
              device_config.get_config("display_type", default="inky"))


def current():
    return _state["font"]


def rendering():
    """Effective rendering: crisp or smooth."""
    if _state["rendering"] != AUTO:
        return _state["rendering"]
    return SMOOTH if _state["display_type"] in SMOOTH_DISPLAYS else CRISP


def auto_rendering_label():
    return SMOOTH if _state["display_type"] in SMOOTH_DISPLAYS else CRISP


def choices():
    return [(key, font["label"]) for key, font in FONTS.items()]


def overrides_template_font():
    """True when the templates' text is not rendered as before (Jost web font, smoothed)."""
    return not (_state["font"] == JOST and rendering() == SMOOTH)


def pil_font_path(weight="normal"):
    """File for Pillow-drawn text in the template family, None to keep Jost."""
    files = FONTS[_state["font"]]["files"]
    name = files.get("bold" if weight == "bold" else "normal") or files.get("normal")
    return os.path.join(FONT_DIR, name) if name else None


def fontconfig_xml(font_key, render):
    font = FONTS[font_key]
    family = escape(font["family"])
    crisp = render == CRISP
    alias = "" if font["family"] == TEMPLATE_FAMILY else f"""
  <!-- the templates' font family is rendered with the chosen font -->
  <match target="pattern">
    <test name="family"><string>{TEMPLATE_FAMILY}</string></test>
    <edit name="family" mode="assign" binding="strong"><string>{family}</string></edit>
  </match>"""
    return f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
  <dir>{escape(FONT_DIR)}</dir>
  <dir>{escape(JOST_DIR)}</dir>{alias}
  <!-- light weights become regular: hairlines break up on e-paper -->
  <match target="pattern">
    <test name="family"><string>{family}</string></test>
    <test name="weight" compare="less"><const>regular</const></test>
    <edit name="weight" mode="assign"><const>regular</const></edit>
  </match>
  <!-- {"monochrome, fully hinted text: stems on whole pixels" if crisp else "grey anti-aliasing"} -->
  <match target="font">
    <edit name="antialias" mode="assign"><bool>{"false" if crisp else "true"}</bool></edit>
    <edit name="hinting" mode="assign"><bool>true</bool></edit>
    <edit name="hintstyle" mode="assign"><const>{"hintfull" if crisp else "hintslight"}</const></edit>
    <edit name="rgba" mode="assign"><const>none</const></edit>
  </match>
  <match target="font">
    <test name="family"><string>{family}</string></test>
    <edit name="autohint" mode="assign"><bool>{"true" if font["autohint"] and crisp else "false"}</bool></edit>
  </match>
</fontconfig>
"""


def browser_env():
    """Environment for the headless browser, None to keep the default rendering."""
    if not overrides_template_font():
        return None
    font_key, render = _state["font"], rendering()
    directory = os.path.join(tempfile.gettempdir(), "inkypi-fontconfig")
    path = os.path.join(directory, f"{font_key}-{render}.conf")
    try:
        os.makedirs(directory, exist_ok=True)
        xml = fontconfig_xml(font_key, render)
        if not os.path.exists(path) or open(path, encoding="utf-8").read() != xml:
            with open(path, "w", encoding="utf-8") as f:
                f.write(xml)
    except OSError as e:
        logger.warning(f"Could not write the fontconfig file, keeping the default font: {e}")
        return None
    return {**os.environ, "FONTCONFIG_FILE": path}
