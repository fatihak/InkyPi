"""Browser-free renderer for the weather plugin.

Draws the same dashboard as render/weather.html + weather.css with Pillow, so
the plugin works on boards where no headless browser runs (e.g. the ARMv6
Raspberry Pi Zero W / Pi 1, where current Chromium and Firefox builds crash
with "Illegal instruction").

It takes the exact template_params that weather.py builds for the HTML
template, so both renderers always show the same data.
"""

import logging
import math
import os
from functools import lru_cache

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from utils.app_utils import resolve_path

logger = logging.getLogger(__name__)

FONT_DIR = resolve_path(os.path.join("static", "fonts"))

# Metrics left off the screen (labels as weather.py names them: "Sunrise",
# "Sunset", "Wind", "Humidity", "Pressure", "UV Index", "Visibility",
# "Air Quality"). Remove a name to bring that metric back.
HIDDEN_METRICS = {"Visibility", "Pressure"}

# Shorter labels shown on screen for some metrics (display only),
# e.g. {"Air Quality": "AQI"}.
LABEL_ABBREVIATIONS = {}
# Shorter rating words after the air-quality number (display only).
AQ_RATING_ABBREVIATIONS = {"Moderate": "Mod", "Very Poor": "V Poor"}

# Deepen the colours of the large current-conditions icon and outline it in
# the text colour, so pale icons (e.g. the night crescent) show up on e-ink.
BOOST_CURRENT_ICON = True
# Dark outline around the large current-conditions icon: "night" outlines only
# the night icons (pale moon), True outlines every icon, False none.
OUTLINE_CURRENT_ICON = "night"

# Where the moon (% lit + next moonrise/moonset) goes: True = under the weather
# icon, keeping the temperature column large; False = under the high/low.
MOON_UNDER_ICON = True

# Chart colours, straight from the Chart.js config in weather.html
LINE_COLOR = (241, 122, 36, 230)
TEMP_FILL = (252, 204, 5)
PRECIP_TOP = (26, 111, 176)
PRECIP_BOTTOM = (194, 223, 246)


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

WEIGHTS = {"light": 300, "normal": 400, "bold": 600}

# Text is rasterised at SS x size and scaled down. Pillow's basic layout snaps
# every glyph to whole pixels, which at small sizes produces uneven gaps
# ("Hum idity"); supersampling gives browser-like spacing and anti-aliasing.
SS = 3
_FONT_META = {}


def _font(family, weight, size):
    font = _load_font(family, weight, max(6, int(round(size))))
    return font


@lru_cache(maxsize=512)
def _load_font(family, weight, size):
    font = _make_font(family, weight, size)
    _FONT_META[id(font)] = (family, weight, size)
    return font


def _big(font):
    family, weight, size = _FONT_META[id(font)]
    return _load_font(family, weight, size * SS)


def _make_font(family, weight, size):
    if family == "Dogica":
        name = "dogicapixelbold.ttf" if weight == "bold" else "dogicapixel.ttf"
        return ImageFont.truetype(os.path.join(FONT_DIR, name), size)

    font = ImageFont.truetype(os.path.join(FONT_DIR, "Jost.ttf"), size)
    try:
        # Jost.ttf is a variable font; pick the CSS weight on its wght axis.
        font.set_variation_by_axes([WEIGHTS.get(weight, 400)])
    except Exception:
        if weight == "bold":
            font = ImageFont.truetype(os.path.join(FONT_DIR, "Jost-SemiBold.ttf"), size)
    return font


def _text_w(font, text):
    if not text:
        return 0
    return _big(font).getlength(text) / SS


def _draw_text(img, xy, text, font, color, anchor="la"):
    """Draw text with sub-pixel placement (see SS)."""
    if not text:
        return
    big = _big(font)
    l, t, r, b = big.getbbox(text, anchor=anchor)
    pad = SS * 2
    fx = xy[0] + (l - pad) / SS
    fy = xy[1] + (t - pad) / SS
    ix, iy = math.floor(fx), math.floor(fy)
    dx, dy = (fx - ix) * SS, (fy - iy) * SS
    mw = math.ceil((r - l + 2 * pad + dx) / SS) * SS
    mh = math.ceil((b - t + 2 * pad + dy) / SS) * SS
    mask = Image.new("L", (mw, mh), 0)
    ImageDraw.Draw(mask).text((pad - l + dx, pad - t + dy), text, font=big, fill=255, anchor=anchor)
    mask = mask.reduce(SS)
    img.paste(Image.new("RGBA", mask.size, tuple(color[:3]) + (255,)), (ix, iy), mask)


def _fit(family, weight, size, text, max_w):
    """Largest font <= size whose rendering of text fits in max_w."""
    size = max(6, size)
    font = _font(family, weight, size)
    w = _text_w(font, text)
    if w > max_w > 0:
        size = max(6, size * max_w / w)
        font = _font(family, weight, size)
    return font


def _parse_color(value, default):
    try:
        return ImageColor.getrgb(value) if value else default
    except (ValueError, AttributeError):
        return default


def _px(settings, key, fallback_key="margin", default=5):
    raw = settings.get(key) or settings.get(fallback_key) or default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Icons
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _load_icon(path):
    try:
        with Image.open(path) as img:
            return img.convert("RGBA")
    except Exception as e:
        logger.warning(f"Could not load icon {path}: {e}")
        return None


def _eink_boost(icon, outline_px, outline_color):
    """Make a pastel icon read well on colour e-ink.

    Pale colours (the light-yellow moon, pale-blue clouds) get dithered into
    sparse dots against white. Deepen and saturate the colours toward the
    panel's solid inks, and trace a dark outline so the shape stays crisp.
    """
    alpha = icon.getchannel("A")
    # Work in HSV: push pale (low-saturation) colours toward full colour so
    # they land on solid ink instead of ink+white dither, and dim only those
    # pale tones slightly. Already-strong colours (e.g. the sun) stay bright.
    h, sat, val = icon.convert("RGB").convert("HSV").split()
    sat = sat.point(lambda v: min(255, int(v + (255 - v) * 0.45)))
    pale = icon.convert("RGB").convert("HSV").getchannel("S").point(lambda v: 255 if v < 120 else 0)
    val = Image.composite(val.point(lambda v: int(v * 0.9)), val, pale)
    rgb = Image.merge("HSV", (h, sat, val)).convert("RGB")
    out = Image.merge("RGBA", (*rgb.split(), alpha))
    if outline_px > 0:
        pad = outline_px + 2
        base = Image.new("RGBA", (out.width + 2 * pad, out.height + 2 * pad), (0, 0, 0, 0))
        a = Image.new("L", base.size, 0)
        a.paste(alpha, (pad, pad))
        ring = a.point(lambda v: 255 if v > 96 else 0).filter(ImageFilter.MaxFilter(2 * outline_px + 1))
        base.paste(Image.new("RGBA", base.size, tuple(outline_color[:3]) + (255,)), (0, 0), ring)
        base.alpha_composite(out, (pad, pad))
        out = base.crop((pad - outline_px, pad - outline_px,
                         pad + icon.width + outline_px, pad + icon.height + outline_px))
    return out


def _paste_contain(canvas, path, box, align="center", boost=False, outline_color=(0, 0, 0)):
    """Paste an icon scaled to fit box (object-fit: contain). Returns the rect used."""
    x, y, w, h = [int(round(v)) for v in box]
    icon = _load_icon(path) if path else None
    if icon is None or w < 2 or h < 2:
        return (x, y, 0, 0)
    scale = min(w / icon.width, h / icon.height)
    iw, ih = max(1, int(icon.width * scale)), max(1, int(icon.height * scale))
    resized = icon.resize((iw, ih), Image.LANCZOS)
    if boost:
        o = max(2, round(min(iw, ih) / 55)) if outline_color is not None else 0  # ~3px on a 150px icon
        resized = _eink_boost(resized, o, outline_color)
        iw, ih = resized.size
        ox = x + (w - iw) // 2 if align == "center" else x
        oy = y + (h - ih) // 2
        canvas.alpha_composite(resized, (max(0, ox), max(0, oy)))
        return (ox, oy, iw, ih)
    ox = x + (w - iw) // 2 if align == "center" else x
    oy = y + (h - ih) // 2
    canvas.alpha_composite(resized, (ox, oy))
    return (ox, oy, iw, ih)


# ---------------------------------------------------------------------------
# Moon drawn from the actual illumination
# ---------------------------------------------------------------------------

MOON_LIT = (255, 214, 40)       # strong yellow: lands on the panel's yellow ink
MOON_DARK = (62, 58, 78)        # dark side


def _moon_lit_right(icon_path):
    """Which limb is lit, from the phase icon's name. weather.py already swaps
    waxing/waning names for the southern hemisphere, so this is the visual side."""
    name = os.path.basename(str(icon_path or "")).lower()
    return not ("waning" in name or "lastquarter" in name)


def _draw_moon(canvas, box, pct, lit_right=True):
    """Draw a moon whose lit area is `pct` percent of the disc."""
    x, y, w, h = box
    size = int(round(min(w, h)))
    if size < 4:
        return
    try:
        k = min(1.0, max(0.0, float(pct) / 100.0))
    except (TypeError, ValueError):
        return
    S = 4
    D = size * S
    R = D / 2 - S
    c = D / 2
    m = Image.new("RGBA", (D, D), (0, 0, 0, 0))
    d = ImageDraw.Draw(m)
    d.ellipse([c - R, c - R, c + R, c + R], fill=MOON_DARK + (255,))
    side = 1 if lit_right else -1
    steps = 90
    term, limb = [], []
    for i in range(steps + 1):
        yy = -R + 2 * R * i / steps
        wx = math.sqrt(max(0.0, R * R - yy * yy))
        # terminator at x = wx * (1 - 2k): lit area between it and the limb is
        # exactly k of the disc (0 = new, 0.5 = quarter, 1 = full)
        term.append((c + side * wx * (1 - 2 * k), c + yy))
        limb.append((c + side * wx, c + yy))
    if k > 0.005:
        d.polygon(term + limb[::-1], fill=MOON_LIT + (255,))
    rim = max(1, round(D / 70))
    d.ellipse([c - R, c - R, c + R, c + R], outline=MOON_DARK + (255,), width=rim)
    m = m.resize((size, size), Image.LANCZOS)
    canvas.alpha_composite(m, (int(round(x + (w - size) / 2)), int(round(y + (h - size) / 2))))


def _paste_moon(canvas, icon_path, pct, box):
    """Procedural moon when the percentage is known, else the phase icon."""
    try:
        float(pct)
    except (TypeError, ValueError):
        return _paste_contain(canvas, icon_path, box)
    _draw_moon(canvas, box, pct, _moon_lit_right(icon_path))


# ---------------------------------------------------------------------------
# Small drawing helpers
# ---------------------------------------------------------------------------

def _arrow_angle(arrow):
    # Screen angle (degrees, 0 = pointing right, counter-clockwise) for the
    # unicode arrows weather.py produces. Drawn as shapes because Jost has no
    # arrow glyphs.
    return {"→": 0, "↗": 45, "↑": 90, "↖": 135, "←": 180, "↙": 225, "↓": 270, "↘": 315}.get(arrow)


def _draw_arrow(draw, cx, cy, size, angle_deg, color, width):
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), -math.sin(a)
    half = size / 2
    tip = (cx + dx * half, cy + dy * half)
    tail = (cx - dx * half, cy - dy * half)
    draw.line([tail, tip], fill=color, width=max(1, int(width)))
    head = size * 0.4
    for side in (150, -150):
        b = a + math.radians(side)
        draw.line([tip, (tip[0] + math.cos(b) * head, tip[1] - math.sin(b) * head)],
                  fill=color, width=max(1, int(width)))


def _deg(units):
    return "" if units == "standard" else "°"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class WeatherRenderer:
    def __init__(self, params, dimensions):
        self.p = dict(params)
        # Drop metrics listed in HIDDEN_METRICS so the rest get more room.
        self.p["data_points"] = [dp for dp in params.get("data_points") or []
                                 if dp.get("label") not in HIDDEN_METRICS]
        self.s = params.get("plugin_settings", {}) or {}
        self.W, self.H = int(dimensions[0]), int(dimensions[1])
        self.units = params.get("units", "imperial")
        self.color = _parse_color(self.s.get("textColor"), (0, 0, 0))
        self.family = "Dogica" if self.W <= 250 else "Jost"
        self.vw = self.W / 100
        self.vh = self.H / 100
        # Chart.js uses fixed 12px ticks / 22px icons; scale them with the
        # panel so they stay legible on big screens and fit on tiny ones.
        self.k = min(2.5, max(0.65, min(self.W / 800, self.H / 480)))
        self.min_text = 8 if self.family == "Dogica" else 9

    def on(self, key):
        return str(self.s.get(key, "")).lower() == "true"

    def font(self, weight, size):
        return _font(self.family, weight, size)

    def fit(self, weight, size, text, max_w):
        return _fit(self.family, weight, size, text, max_w)

    def text(self, xy, text, font, fill=None, anchor="la"):
        _draw_text(self.img, xy, text, font, fill or self.color, anchor)

    # -- page ---------------------------------------------------------------
    def render(self):
        img = self._background()
        self.img = img
        self.draw = ImageDraw.Draw(img)

        mt, mb = _px(self.s, "topMargin"), _px(self.s, "bottomMargin")
        ml, mr = _px(self.s, "leftMargin"), _px(self.s, "rightMargin")
        body = (ml, mt, self.W - ml - mr, self.H - mt - mb)
        self._frame(body)

        pad = 1.5 * self.vw
        frame = self.s.get("selectedFrame")
        border = 0.7 * self.vw if frame in ("Rectangle", "Top and Bottom") else 0
        side_border = border if frame == "Rectangle" else 0
        x = body[0] + pad + side_border
        y = body[1] + pad + border
        w = body[2] - 2 * (pad + side_border)
        h = body[3] - 2 * (pad + border)
        self._dashboard(x, y, w, h)
        return img.convert("RGB")

    def _background(self):
        option = self.s.get("backgroundOption")
        img = Image.new("RGBA", (self.W, self.H), (255, 255, 255, 255))
        if option == "color":
            img.paste(_parse_color(self.s.get("backgroundColor"), (255, 255, 255)) + (255,),
                      (0, 0, self.W, self.H))
        elif option == "image" and self.s.get("backgroundImageFile"):
            try:
                with Image.open(self.s["backgroundImageFile"]) as bg:
                    img = ImageOps.fit(bg.convert("RGBA"), (self.W, self.H), Image.LANCZOS)
            except Exception as e:
                logger.warning(f"Could not load background image: {e}")
        return img

    def _frame(self, body):
        x, y, w, h = body
        frame = self.s.get("selectedFrame")
        t = max(1, int(round(0.7 * self.vw)))
        d = self.draw
        if frame == "Rectangle":
            for i in range(t):
                d.rectangle([x + i, y + i, x + w - 1 - i, y + h - 1 - i], outline=self.color)
        elif frame == "Top and Bottom":
            d.rectangle([x, y, x + w - 1, y + t - 1], fill=self.color)
            d.rectangle([x, y + h - t, x + w - 1, y + h - 1], fill=self.color)
        elif frame == "Corner":
            L = 10 * self.vw
            d.rectangle([x, y, x + L, y + t - 1], fill=self.color)
            d.rectangle([x, y, x + t - 1, y + L], fill=self.color)
            t2 = max(1, int(round(0.5 * self.vw)))
            d.rectangle([x + w - L, y + h - t2, x + w - 1, y + h - 1], fill=self.color)
            d.rectangle([x + w - t2, y + h - L, x + w - 1, y + h - 1], fill=self.color)

    # -- layout -------------------------------------------------------------
    def _dashboard(self, x, y, w, h):
        portrait = self.W <= self.H
        gap = 1 * self.vh
        show_metrics = self.on("displayMetrics") and self.p.get("data_points")
        show_graph = self.on("displayGraph") and self.p.get("hourly_forecast")
        show_forecast = self.on("displayForecast") and self._forecast_days()
        # Tiny panels (e.g. 250x122 Inky pHAT): metrics, graph and refresh
        # time can't be legible, so show a compact title/current/forecast view.
        self.compact = min(self.W, self.H) < 160
        if self.compact:
            show_metrics = show_graph = False

        # Without the hourly graph, enlarge the title/date ~20%; the header
        # grows only slightly and the text uses the slack above the title, so
        # the temperature and metrics below keep their size.
        self.big_header = not show_graph and not self.compact
        header_h = (16 if self.big_header else 15) * self.vh
        graph_h = 24 * self.vh if show_graph else 0
        forecast_h = self._forecast_height(w, h) if show_forecast else 0

        if show_metrics and not portrait and forecast_h:
            cols = 3 if self.W / self.H >= 2 else 2
            rows = math.ceil(len(self.p.get("data_points", [])) / cols)
            want = rows * self.min_text * 3.2
            rest = h - header_h - graph_h - forecast_h - 3 * gap
            if rest < want:
                # shrink the forecast icons (down to ~6vh) before dropping metrics
                give = min(want - rest, max(0, min(15 * self.vw, 13 * self.vh) - 6 * self.vh))
                forecast_h -= give

        sections = [s for s in (header_h, graph_h, forecast_h) if s]
        rest = h - sum(sections) - gap * len(sections)
        today_h = max(rest, 10 * self.vh)
        if portrait:
            # Portrait: current conditions stacked above a 4-wide metrics grid
            # (3-wide below 1:2), each metric row 7vh tall like the CSS.
            cols = 3 if self.W / self.H <= 0.5 else 4
            rows = math.ceil(len(self.p.get("data_points", [])) / cols) if show_metrics else 0
            metrics_h = rows * 7 * self.vh + max(0, rows - 1) * 0.5 * self.vh
            today_h = max(today_h, metrics_h + 12 * self.vh)

        cy = y + max(0, (h - (sum(sections) + today_h + gap * len(sections))) / 2)

        self._last_refresh(x, y, w)
        self._header(x, cy, w, header_h)
        cy += header_h + gap
        self._today(x, cy, w, today_h, portrait, show_metrics)
        cy += today_h + gap
        if show_graph:
            self._graph(x, cy, w, graph_h)
            cy += graph_h + gap
        if show_forecast:
            self._forecast(x, cy, w, forecast_h)

    # -- header ---------------------------------------------------------------
    def _last_refresh(self, x, y, w):
        if self.compact or not self.on("displayRefreshTime") or not self.p.get("last_refresh_time"):
            return
        text = f"Last refresh: {self.p['last_refresh_time']}"
        font = self.font("bold", max(self.min_text - 1, min(2 * self.vh, 2 * self.vw)))
        self.text((x + w - 0.5 * self.vw, y + 0.5 * self.vh), text,
                       font=font, fill=self.color, anchor="ra")

    def _header(self, x, y, w, h):
        title = str(self.p.get("title") or "")
        date = str(self.p.get("current_date") or "")
        k_t, k_d = (0.56, 0.34) if getattr(self, "big_header", False) else (0.5, 0.3)
        date_font = self.fit("normal", min(k_d * h, 0.06 * w), date, w)
        title_font = self.fit("bold", min(k_t * h, 0.08 * w), title, w)
        cx = x + w / 2
        bottom = y + h
        if getattr(self, "compact", False):
            date = ""
            title_font = self.fit("bold", min(0.8 * h, 0.08 * w), title, w)
        if date:
            self.text((cx, bottom), date, font=date_font, fill=self.color, anchor="md")
            bottom -= date_font.size * 1.05
        if title:
            self.text((cx, bottom), title, font=title_font, fill=self.color, anchor="md")

    # -- current conditions + metrics ----------------------------------------
    def _today(self, x, y, w, h, portrait, show_metrics):
        if portrait:
            points = self.p.get("data_points", []) if show_metrics else []
            cols = 3 if self.W / self.H <= 0.5 else 4
            rows = math.ceil(len(points) / cols) if points else 0
            metrics_h = rows * 7 * self.vh + max(0, rows - 1) * 0.5 * self.vh
            current_h = h - metrics_h - (1 * self.vh if rows else 0)
            self._current(x, y, w, current_h)
            if rows:
                self._metrics(x, y + current_h + 1 * self.vh, w, metrics_h, cols, rows, points)
        else:
            if show_metrics:
                self._current(x, y, w / 2, h)
                points = self.p.get("data_points", [])
                cols = 3 if self.W / self.H >= 2 else 2
                rows = max(1, math.ceil(len(points) / cols))
                self._metrics(x + w / 2, y, w / 2, h, cols, rows, points)
            else:
                self._current(x + w / 4, y, w / 2, h)

    def _current(self, x, y, w, h):
        pad = 2 * self.vw
        x, w = x + pad, w - 2 * pad
        # Icon gets ~40% of the block so the text column can grow.
        icon_w = w * 0.40
        icon_h = h
        # Under the icon only when there is height for both (not with the graph).
        moon_left = (MOON_UNDER_ICON and not self.compact and h >= 34 * self.vh
                     and self._moon_block_left(x, y, icon_w * 0.92, h))
        if moon_left:
            icon_h = h - moon_left
        _paste_contain(self.img, self.p.get("current_day_icon"), (x, y, icon_w * 0.92, icon_h),
                       boost=BOOST_CURRENT_ICON,
                       outline_color=self.color if self._outline_current_icon() else None)

        bx, bw = x + icon_w, w - icon_w
        deg = _deg(self.units)
        temp = str(self.p.get("current_temperature", ""))
        unit = str(self.p.get("temperature_unit", ""))
        feels = f"Feels Like {self.p.get('feels_like', '')}{deg}"
        today = (self.p.get("forecast") or [{}])[0]
        minmax = f"{today.get('high', '')}{deg} / {today.get('low', '')}{deg}" if today else ""

        # Tonight's moon: phase icon + % illuminated (from today's forecast entry)
        # Prefer live values (illumination now + next rise/set) from weather.py;
        # fall back to today's forecast entry.
        moon_now = self.p.get("moon_now") or {}
        moon_icon = moon_now.get("icon") or (today.get("moon_phase_icon") if today else None)
        moon_pct = moon_now.get("pct") or (today.get("moon_phase_pct") if today else None)
        show_moon = bool(moon_icon and moon_pct not in (None, "")) and not self.compact and not moon_left
        moon_text = f"{moon_pct}% lit" if show_moon else ""
        events = (moon_now.get("events") or []) if show_moon else []
        events_text = "   ".join(f"{e['label']} {e['time']}" for e in events)

        # Size everything from the big temperature, as large as the column
        # allows, then shrink the whole block if it is taller than the space.
        # Two proportion sets: roomy secondary lines when there is space, the
        # original tighter ones when height is short (e.g. graph shown), so
        # the temperature never ends up smaller than before.
        def layout(ratios):
            r_feels, r_minmax, r_moon, r_ev = ratios
            size = min(0.55 * bw, 0.5 * h, 0.24 * min(self.W, self.H))
            for _ in range(5):
                tf = self.font("normal", size)
                uf = self.font("normal", size * 0.4)
                tw_, uw_ = _text_w(tf, temp), _text_w(uf, unit)
                if tw_ + uw_ > bw * 0.98:
                    k = bw * 0.98 / (tw_ + uw_)
                    tf = self.font("normal", size * k)
                    uf = self.font("normal", size * k * 0.4)
                    tw_, uw_ = _text_w(tf, temp), _text_w(uf, unit)
                ts = tf.size
                ff = self.fit("normal", ts * r_feels, feels, bw)
                mf = self.fit("normal", ts * r_minmax, minmax, bw)
                mo = self.fit("normal", ts * r_moon, moon_text, bw * 0.75) if show_moon else None
                mo_h = mo.size * 1.6 if show_moon else 0
                ev = self.fit("normal", ts * r_ev, events_text, bw) if events_text else None
                ev_h = ev.size * 1.35 if ev else 0
                bh = ts + ff.size * 1.4 + mf.size * 1.4 + mo_h + ev_h
                if bh <= h * 0.88:
                    break
                size = ts * (h * 0.88 / bh)
            return dict(temp_font=tf, unit_font=uf, tw=tw_, uw=uw_, feels_font=ff,
                        minmax_font=mf, moon_font=mo, moon_h=mo_h, ev_font=ev, ev_h=ev_h,
                        block_h=bh)

        roomy = layout((0.26, 0.30, 0.28, 0.22))
        tight = layout((0.22, 0.27, 0.27, 0.20))
        chosen = roomy if roomy["temp_font"].size >= 0.95 * tight["temp_font"].size else tight
        temp_font, unit_font = chosen["temp_font"], chosen["unit_font"]
        tw, uw = chosen["tw"], chosen["uw"]
        feels_font, minmax_font = chosen["feels_font"], chosen["minmax_font"]
        moon_font, moon_h, block_h = chosen["moon_font"], chosen["moon_h"], chosen["block_h"]
        ev_font, ev_h = chosen["ev_font"], chosen["ev_h"]
        temp_line = temp_font.size * 1.0
        top = y + (h - block_h) / 2

        # big temperature, unit as a superscript to its right (centered as a pair)
        tx = bx + (bw - tw) / 2
        baseline = top + temp_line * 0.9
        self.text((tx, baseline), temp, font=temp_font, fill=self.color, anchor="ls")
        self.text((tx + tw, baseline - temp_font.size * 0.42), unit,
                       font=unit_font, fill=self.color, anchor="ls")

        cy = top + temp_line + feels_font.size * 0.7
        self.text((bx + bw / 2, cy), feels, font=feels_font, fill=self.color, anchor="mm")
        cy += feels_font.size * 0.7 + minmax_font.size * 0.7
        self.text((bx + bw / 2, cy), minmax, font=minmax_font, fill=self.color, anchor="mm")

        if show_moon:
            cy += minmax_font.size * 0.7 + moon_h / 2
            isz = moon_font.size * 1.35
            gap = moon_font.size * 0.35
            total = isz + gap + _text_w(moon_font, moon_text)
            mx = bx + (bw - total) / 2
            _paste_moon(self.img, moon_icon, moon_pct, (mx, cy - isz / 2, isz, isz))
            self.text((mx + isz + gap, cy), moon_text, font=moon_font, anchor="lm")
            if ev_font:
                # next moonrise / moonset, soonest first
                cy += moon_h / 2 + ev_h / 2
                self.text((bx + bw / 2, cy), events_text, font=ev_font, anchor="mm")

    def _moon_block_left(self, x, y, w, h):
        """Draw moon % and next rise/set under the weather icon.

        Returns the height used (0 if there is nothing to show)."""
        today = (self.p.get("forecast") or [{}])[0] or {}
        moon_now = self.p.get("moon_now") or {}
        icon = moon_now.get("icon") or today.get("moon_phase_icon")
        pct = moon_now.get("pct") or today.get("moon_phase_pct")
        if not icon or pct in (None, ""):
            return 0
        pct_text = f"{pct}% lit"
        lines = [f"{e['label']} {e['time']}" for e in (moon_now.get("events") or [])]

        # Size from the space, then fit the widest line to the column.
        s1 = min(0.12 * h, 0.2 * w)
        k = w / max(1, s1 * 1.7 + _text_w(self.font("normal", s1), pct_text))
        s1 = s1 * min(1.0, k)
        f1 = self.font("normal", s1)
        f2 = None
        if lines:
            widest = max(lines, key=lambda t: _text_w(self.font("normal", 20), t))
            f2 = self.fit("normal", min(0.095 * h, s1 * 0.9), widest, w)
        block = f1.size * 1.55 + (len(lines) * f2.size * 1.3 if f2 else 0)
        top = y + h - block
        cx = x + w / 2

        cy = top + f1.size * 0.75
        isz = f1.size * 1.35
        gap = f1.size * 0.35
        total = isz + gap + _text_w(f1, pct_text)
        mx = cx - total / 2
        _paste_moon(self.img, icon, pct, (mx, cy - isz / 2, isz, isz))
        self.text((mx + isz + gap, cy), pct_text, font=f1, anchor="lm")
        cy += f1.size * 0.8
        for t in lines:
            cy += f2.size * 0.65
            self.text((cx, cy), t, font=f2, anchor="mm")
            cy += f2.size * 0.65
        return block + 0.5 * self.vh

    def _outline_current_icon(self):
        if OUTLINE_CURRENT_ICON == "night":
            # night icons are named like 01n.png / 022n.png (moon instead of sun)
            name = os.path.basename(str(self.p.get("current_day_icon") or ""))
            return os.path.splitext(name)[0].endswith("n")
        return bool(OUTLINE_CURRENT_ICON)

    def _metrics(self, x, y, w, h, cols, rows, points):
        gx, gy = 1 * self.vw, 0.5 * self.vh
        # Small panels: drop trailing metrics rather than shrink text to mush.
        min_cell = self.min_text * 2.6
        rows = max(0, min(rows, int((h + gy) // (min_cell + gy))))
        if rows == 0:
            return
        cell_w = (w - gx * (cols - 1)) / cols
        cell_h = min((h * 0.95 - gy * (rows - 1)) / rows, 20 * self.vh)
        grid_h = rows * cell_h + (rows - 1) * gy
        y += (h - grid_h) / 2
        for i, dp in enumerate(points[: cols * rows]):
            r, c = divmod(i, cols)
            self._metric(x + c * (cell_w + gx), y + r * (cell_h + gy), cell_w, cell_h, dp)

    def _metric(self, x, y, w, h, dp):
        icon_w = w * 0.24
        _paste_contain(self.img, dp.get("icon"), (x, y + h * 0.12, icon_w, h * 0.76))

        pad = 0.8 * self.vw  # keep values clear of the icon
        tx, tw = x + icon_w + pad, w - icon_w - pad
        label = str(dp.get("label", ""))
        meas = "" if dp.get("measurement") is None else str(dp.get("measurement"))
        is_wind = label == "Wind"
        is_aq = label == "Air Quality"
        label = LABEL_ABBREVIATIONS.get(label, label)
        unit = str(dp.get("unit") or "")
        if is_aq:
            unit = AQ_RATING_ABBREVIATIONS.get(unit, unit)
        arrow = dp.get("arrow") if is_wind else None
        angle = _arrow_angle(arrow) if arrow else None

        label_font = self.fit("light", max(self.min_text, min(0.35 * h, 0.19 * tw)), label, tw)
        m_size = max(self.min_text, min(0.54 * h, 0.36 * tw))
        m_font = self.font("bold", m_size)
        # UV shows "/ 5.8 max" here: regular weight so the peak stays legible
        u_weight = "normal" if dp.get("uv_max") is not None else "light"
        u_font = self.font(u_weight, m_size * 0.6)
        gap_u = 0.2 * self.vw if unit else 0
        arrow_w = m_size * 0.8 if angle is not None else 0
        total = _text_w(m_font, meas) + gap_u + _text_w(u_font, unit) + (arrow_w + m_size * 0.2 if arrow_w else 0)
        if total > tw:
            k = tw / total
            m_size *= k
            m_font, u_font = self.font("bold", m_size), self.font(u_weight, m_size * 0.6)
            gap_u *= k
            arrow_w *= k
            total = tw

        # Label directly above its value, the pair centred in the cell (the
        # label used to sit at the cell's top 30%, far from a small value).
        cap = m_size * 0.72                   # height of digits above the baseline
        l_cap = label_font.size * 0.72        # height of the label's capitals
        gap_lv = max(2, label_font.size * 0.32)
        block = l_cap + gap_lv + cap
        top = y + (h - block) / 2
        # anchor on the label's baseline so descenders (the y in "Quality")
        # don't push it away from its value
        self.text((tx + tw / 2, top + l_cap), label, font=label_font, fill=self.color, anchor="ms")
        baseline = top + l_cap + gap_lv + cap
        cx = tx + (tw - total) / 2
        self.text((cx, baseline), meas, font=m_font, fill=self.color, anchor="ls")
        cx += _text_w(m_font, meas) + gap_u
        if unit:
            self.text((cx, baseline), unit, font=u_font, fill=self.color, anchor="ls")
            cx += _text_w(u_font, unit)
        if angle is not None:
            cx += m_size * 0.2
            _draw_arrow(self.draw, cx + arrow_w / 2, baseline - m_size * 0.35, arrow_w * 0.85,
                        angle, self.color, max(1, m_size / 9))

    # -- hourly graph ---------------------------------------------------------
    def _graph(self, x, y, w, h):
        hours = self.p.get("hourly_forecast", [])
        temps = [float(hr.get("temperature", 0) or 0) for hr in hours]
        precip = [max(0.0, min(100.0, float(hr.get("precipitation") or 0) * 100)) for hr in hours]
        rain = [float(hr.get("rain") or 0) for hr in hours]
        labels = [str(hr.get("time", "")) for hr in hours]
        n = len(temps)
        if n < 2:
            return

        k = self.k
        tick = self.font("normal", max(self.min_text, 12 * k))
        deg = _deg(self.units)
        t_min, t_max = min(temps), max(temps)
        fmt = lambda v: f"{int(v) if float(v).is_integer() else v}{deg}"
        icons = self.on("displayGraphIcons")
        step = 2
        try:
            step = max(1, int(self.s.get("graphIconStep") or 2))
        except (TypeError, ValueError):
            pass

        left = x + max(_text_w(tick, fmt(t_max)), _text_w(tick, fmt(t_min))) + 5 * k + 2
        right = x + w - _text_w(tick, "100%") - 2
        top = y + (3 if icons else 0) + tick.size / 2
        label_h = tick.size + 10 * k
        isz = int(round(22 * k))
        icon_h = isz + 4 * k if icons else 0
        bottom = y + h - label_h - icon_h
        bottom = max(top + 10, bottom)
        cw, ch = right - left, bottom - top
        slot = cw / n
        xs = [left + slot * (i + 0.5) for i in range(n)]

        span = (t_max - t_min) or 1.0

        def ty(v):
            return bottom - (v - t_min) / span * ch

        def py(v):
            return bottom - v / 100 * ch

        layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))

        # precipitation bars (drawn first: Chart.js puts dataset 0 on top)
        bar_mask = Image.new("L", self.img.size, 0)
        bm = ImageDraw.Draw(bar_mask)
        tops = []
        for i, v in enumerate(precip):
            if v <= 0:
                continue
            x0, x1 = left + slot * i, left + slot * (i + 1)
            bm.rectangle([x0, py(v), x1, bottom], fill=255)
            tops.append((x0, py(v), x1))
        grad = self._vgradient(top, bottom, PRECIP_TOP + (204,), PRECIP_BOTTOM + (0,))
        layer = Image.composite(grad, layer, bar_mask)
        ld = ImageDraw.Draw(layer)
        for x0, yt, x1 in tops:
            ld.rectangle([x0, yt, x1, yt + 1], fill=PRECIP_TOP + (255,))

        # temperature curve with gradient fill (Chart.js tension 0.5 spline)
        curve = self._spline([(xs[i], ty(t)) for i, t in enumerate(temps)], 0.5, top, bottom)
        origin = ty(min(max(0.0, t_min), t_max)) if t_min < 0 < t_max else bottom
        fill_mask = Image.new("L", self.img.size, 0)
        ImageDraw.Draw(fill_mask).polygon(curve + [(xs[-1], origin), (xs[0], origin)], fill=255)
        tgrad = self._vgradient(top, bottom + 10, TEMP_FILL + (242,), TEMP_FILL + (3,))
        temp_layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        temp_layer = Image.composite(tgrad, temp_layer, fill_mask)
        layer = Image.alpha_composite(layer, temp_layer)
        ImageDraw.Draw(layer).line(curve, fill=LINE_COLOR, width=2, joint="curve")

        self.img.alpha_composite(layer)
        d = self.draw

        # axes labels: only min/max temp on the left and 0%/100% on the right
        self.text((left - 5 * k, top), fmt(t_max), font=tick, fill=self.color, anchor="rm")
        self.text((left - 5 * k, bottom), fmt(t_min), font=tick, fill=self.color, anchor="rm")
        self.text((right + 2, top), "100%", font=tick, fill=self.color, anchor="lm")
        self.text((right + 2, bottom), "0%", font=tick, fill=self.color, anchor="lm")

        # x labels, auto-skipped so they never overlap (like Chart.js autoSkip)
        widest = max(_text_w(tick, s) for s in labels) + 6
        skip = max(1, math.ceil(widest / slot))
        for i in range(0, n, skip):
            self.text((xs[i], bottom + 10 * k), labels[i], font=tick, fill=self.color, anchor="mt")

        if icons:
            for i in range(0, n, step):
                _paste_contain(self.img, hours[i].get("icon"),
                               (xs[i] - isz / 2, bottom + label_h + 2 * k, isz, isz))

        if self.on("displayRain"):
            imperial = self.units == "imperial"
            unit, threshold = ("in", 0.0035) if imperial else ("mm", 0.09)
            small = self.font("normal", max(self.min_text - 1, 10 * k))
            for i, r in enumerate(rain):
                if r > threshold:
                    yt = py(precip[i])
                    if bottom - yt < 25 * k:
                        ty1, ty2 = yt - 10 * k, yt - 3 * k
                    else:
                        ty1, ty2 = yt + 13 * k, yt + 20 * k
                    self.text((xs[i], ty1), f"{r:.2f}", font=small, fill=self.color, anchor="ms")
                    self.text((xs[i], ty2), unit, font=small, fill=self.color, anchor="ms")

    def _vgradient(self, y0, y1, c0, c1):
        """Full-canvas RGBA image with a vertical gradient from c0 at y0 to c1 at y1."""
        W, H = self.img.size
        col = Image.new("RGBA", (1, H))
        span = max(1.0, y1 - y0)
        px = col.load()
        for yy in range(H):
            t = min(1.0, max(0.0, (yy - y0) / span))
            px[0, yy] = tuple(int(round(c0[k] + (c1[k] - c0[k]) * t)) for k in range(4))
        return col.resize((W, H))

    @staticmethod
    def _spline(points, tension, top, bottom, samples=12):
        """Chart.js-style cubic Bezier through points, capped to the chart area."""
        n = len(points)
        cps = []
        for i in range(n):
            p0 = points[max(0, i - 1)]
            p1 = points[i]
            p2 = points[min(n - 1, i + 1)]
            d01 = math.dist(p0, p1)
            d12 = math.dist(p1, p2)
            s01 = d01 / (d01 + d12) if d01 + d12 else 0
            s12 = d12 / (d01 + d12) if d01 + d12 else 0
            fa, fb = tension * s01, tension * s12
            prev = (p1[0] - fa * (p2[0] - p0[0]), p1[1] - fa * (p2[1] - p0[1]))
            nxt = (p1[0] + fb * (p2[0] - p0[0]), p1[1] + fb * (p2[1] - p0[1]))
            cap = lambda p: (p[0], min(bottom, max(top, p[1])))
            cps.append((cap(prev), cap(nxt)))
        out = [points[0]]
        for i in range(n - 1):
            a, b = points[i], points[i + 1]
            c1, c2 = cps[i][1], cps[i + 1][0]
            for k in range(1, samples + 1):
                t = k / samples
                mt = 1 - t
                out.append((
                    mt ** 3 * a[0] + 3 * mt * mt * t * c1[0] + 3 * mt * t * t * c2[0] + t ** 3 * b[0],
                    mt ** 3 * a[1] + 3 * mt * mt * t * c1[1] + 3 * mt * t * t * c2[1] + t ** 3 * b[1],
                ))
        return out

    # -- daily forecast -------------------------------------------------------
    def _forecast_days(self):
        try:
            count = int(self.s.get("forecastDays") or 0)
        except (TypeError, ValueError):
            count = 0
        return (self.p.get("forecast") or [])[1:count + 1]

    def _forecast_fonts(self):
        name = self.font("bold", max(self.min_text, min(3.5 * self.vh, 3.5 * self.vw)))
        temps = self.font("normal", max(self.min_text, min(3 * self.vh, 2.5 * self.vw)))
        return name, temps

    def _forecast_height(self, w, h):
        name, temps = self._forecast_fonts()
        icon = min(15 * self.vw, 13 * self.vh)
        moon = (4 * self.vw + 3 + 0.5 * self.vh) if self.on("moonPhase") else 0
        return 2 * self.vh + name.size + icon + temps.size * 1.25 + 3 * 0.5 * self.vh + moon

    def _forecast(self, x, y, w, h):
        days = self._forecast_days()
        name_font, temps_font = self._forecast_fonts()
        deg = _deg(self.units)
        gap = 1.5 * self.vw
        pad_x, pad_y = 1 * self.vw, 1 * self.vh
        moon = self.on("moonPhase")

        texts = [(str(d.get("day", "")), f"{d.get('high', '')}{deg} / {d.get('low', '')}{deg}") for d in days]
        # Small panels: show only as many days as fit without squashing text.
        need = max(_text_w(temps_font, b) for _, b in texts) + 2 * pad_x
        fit_n = max(1, int((w + gap) // (need + gap)))
        days, texts = days[:fit_n], texts[:fit_n]
        n = len(days)
        icon_max = min(15 * self.vw, 13 * self.vh)
        content_w = max(max(_text_w(name_font, a), _text_w(temps_font, b)) for a, b in texts)
        box_w = min(max(content_w, icon_max * 0.8) + 2 * pad_x, (w - gap * (n - 1)) / n)
        free = w - n * box_w
        spacing = free / (n + 1)  # justify-content: space-evenly

        radius = max(2, int(1.2 * self.vw))

        # Few days (e.g. 3): widen the cards to share the row, and once a card
        # is much wider than tall, put a large icon beside the text so it can
        # use nearly the full card height.
        wide_w = min((w - gap * (n + 1)) / n, 32 * self.vw)
        if n <= 4 and wide_w >= 1.8 * h:
            self._forecast_wide(x, y, w, h, days, texts, wide_w, gap, pad_x, pad_y, radius, moon)
            return

        icon_h = h - 2 * pad_y - name_font.size - temps_font.size * 1.25 - 2 * 0.5 * self.vh
        if moon:
            icon_h -= 4 * self.vw + 3 + 0.5 * self.vh
        icon_h = max(8, icon_h)

        for i, (day, (name, temps)) in enumerate(zip(days, texts)):
            bx = x + spacing + i * (box_w + spacing)
            self.draw.rounded_rectangle([bx, y, bx + box_w, y + h - 1], radius=radius,
                                        outline=self.color, width=1)
            cx = bx + box_w / 2
            cy = y + pad_y
            f = _fit(self.family, "bold", name_font.size, name, box_w - 2 * pad_x)
            self.text((cx, cy + name_font.size / 2), name, font=f, fill=self.color, anchor="mm")
            cy += name_font.size + 0.5 * self.vh
            iw = min(box_w - 2 * pad_x, icon_max)
            _paste_contain(self.img, day.get("icon"), (cx - iw / 2, cy, iw, icon_h))
            cy += icon_h + 0.5 * self.vh
            f = _fit(self.family, "normal", temps_font.size, temps, box_w - 2 * pad_x)
            self.text((cx, cy + temps_font.size * 0.6), temps, font=f, fill=self.color, anchor="mm")
            cy += temps_font.size * 1.25
            if moon:
                self.draw.line([bx + box_w * 0.05, cy + 3, bx + box_w * 0.95, cy + 3], fill=(170, 170, 170), width=1)
                cy += 3 + 0.5 * self.vh
                ms = 4 * self.vw
                pct = f"{day.get('moon_phase_pct', '')} %"
                pf = self.font("normal", min(temps_font.size, ms * 0.8))
                total = ms + 10 + _text_w(pf, pct)
                mx = cx - total / 2
                _paste_moon(self.img, day.get("moon_phase_icon"), day.get("moon_phase_pct"), (mx, cy, ms, ms))
                self.text((mx + ms + 10, cy + ms / 2), pct, font=pf, fill=self.color, anchor="lm")

    def _forecast_wide(self, x, y, w, h, days, texts, box_w, gap, pad_x, pad_y, radius, moon):
        n = len(days)
        spacing = (w - n * box_w) / (n + 1)  # justify-content: space-evenly
        icon = h - 2 * pad_y
        for i, (day, (name, temps)) in enumerate(zip(days, texts)):
            bx = x + spacing + i * (box_w + spacing)
            self.draw.rounded_rectangle([bx, y, bx + box_w, y + h - 1], radius=radius,
                                        outline=self.color, width=1)
            # icon on the left, as large as the card allows
            iw = min(icon, (box_w - 3 * pad_x) * 0.5)
            _paste_contain(self.img, day.get("icon"), (bx + pad_x, y + pad_y, iw, icon))

            # day name and temperatures centred in the remaining column
            tx = bx + 2 * pad_x + iw
            tw = bx + box_w - pad_x - tx
            cx = tx + tw / 2
            name_f = self.fit("bold", h * (0.30 if moon else 0.34), name, tw)
            temps_f = self.fit("normal", h * (0.22 if moon else 0.26), temps, tw)
            moon_sz = h * 0.2 if moon else 0
            block = name_f.size * 1.15 + temps_f.size * 1.2 + (moon_sz + 0.5 * self.vh if moon else 0)
            cy = y + (h - block) / 2
            self.text((cx, cy + name_f.size * 0.55), name, font=name_f, anchor="mm")
            cy += name_f.size * 1.15
            self.text((cx, cy + temps_f.size * 0.6), temps, font=temps_f, anchor="mm")
            cy += temps_f.size * 1.2
            if moon:
                cy += 0.5 * self.vh
                pct = f"{day.get('moon_phase_pct', '')} %"
                pf = self.font("normal", moon_sz * 0.8)
                total = moon_sz + 8 + _text_w(pf, pct)
                mx = cx - total / 2
                _paste_moon(self.img, day.get("moon_phase_icon"), day.get("moon_phase_pct"), (mx, cy, moon_sz, moon_sz))
                self.text((mx + moon_sz + 8, cy + moon_sz / 2), pct, font=pf, anchor="lm")


def render_weather(template_params, dimensions):
    """Render the weather dashboard to a PIL image without a browser."""
    return WeatherRenderer(template_params, dimensions).render()
