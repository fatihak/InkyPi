import logging
from datetime import datetime

import pytz
from PIL import Image, ImageDraw

from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import get_font

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "US/Eastern"

# Colors matching the reference widget
BG_COLOR = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (204, 50, 50)
LIGHT_GRAY = (180, 180, 180)
TRACK = (50, 50, 50)
GHOST = (25, 25, 25)


class Today(BasePlugin):
    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        tz_name = device_config.get_config("timezone") or DEFAULT_TIMEZONE
        tz = pytz.timezone(tz_name)
        now = datetime.now(tz)

        # Full day progress (00:00 to 23:59)
        total_day = 23 * 60 + 59
        cur = now.hour * 60 + now.minute
        progress = min(cur / total_day, 1.0)
        remaining = max(total_day - cur, 0)

        # Format time (12h, no leading zero on hour)
        hour = now.hour % 12 or 12
        period = "AM" if now.hour < 12 else "PM"
        time_digits = f"{hour}:{now.minute:02d}"

        # Date in uppercase: MONDAY, MAR 2
        date_str = now.strftime("%A, %b %-d").upper()

        # Remaining time
        h, m = divmod(remaining, 60)
        remain_str = f"{h}h {m:02d}m left" if h > 0 else f"{m}m left"

        return self._render(dimensions, time_digits, period, date_str, progress, remain_str)

    def _render(self, dimensions, time_digits, period, date_str, progress, remain_str):
        w, h = dimensions
        img = Image.new("RGBA", (w, h), BG_COLOR + (255,))
        draw = ImageDraw.Draw(img)

        # Flat black card with rounded corners
        mx, my = int(w * 0.04), int(h * 0.04)
        cw, ch = w - 2 * mx, h - 2 * my
        radius = int(min(cw, ch) * 0.06)
        draw.rounded_rectangle([mx, my, mx + cw, my + ch], radius=radius, fill=BG_COLOR)

        cx = w // 2
        dim = min(cw, ch)

        # Fonts — pushed slightly larger while preserving hierarchy
        title_fnt = get_font("Jost", int(dim * 0.09), "bold")
        clock_fnt = get_font("DS-Digital", int(dim * 0.50))
        period_fnt = get_font("Jost", int(dim * 0.082), "bold")
        date_fnt = get_font("Jost", int(dim * 0.10), "bold")
        remain_fnt = get_font("Jost", int(dim * 0.072))

        # Vertical layout positions
        y_title = my + int(ch * 0.075)
        y_clock = my + int(ch * 0.35)
        y_date = y_clock + int(ch * 0.30)
        y_bar = y_date + int(ch * 0.16)
        y_remain = y_bar + int(ch * 0.14)

        # --- TODAY label ---
        draw.text((cx, y_title), "TODAY", font=title_fnt, fill=WHITE, anchor="mm")

        # --- Clock ---
        d_w = draw.textlength(time_digits, font=clock_fnt)
        p_w = draw.textlength(period, font=period_fnt)
        gap = int(dim * 0.015)
        total_w = d_w + gap + p_w
        sx = cx - total_w / 2

        # Ghost digits (dim segments behind active digits)
        ghost = ''.join('8' if c.isdigit() else c for c in time_digits)
        draw.text((sx, y_clock), ghost, font=clock_fnt, fill=GHOST, anchor="lm")

        # Active time digits
        draw.text((sx, y_clock), time_digits, font=clock_fnt, fill=WHITE, anchor="lm")

        # AM/PM — smaller, aligned to digit baseline area
        draw.text((sx + d_w + gap, y_clock), period, font=period_fnt, fill=WHITE, anchor="lm")

        # --- Date line in light gray ---
        draw.text((cx, y_date), date_str, font=date_fnt, fill=LIGHT_GRAY, anchor="mm")

        # --- Progress bar ---
        bar_w = int(cw * 0.60)
        bar_h = int(dim * 0.04)
        bar_x = cx - bar_w // 2
        bar_r = bar_h // 2

        # Track
        draw.rounded_rectangle(
            [bar_x, y_bar - bar_h // 2, bar_x + bar_w, y_bar + bar_h // 2],
            radius=bar_r, fill=TRACK + (255,)
        )

        # Fill
        if progress > 0:
            fill_w = max(int(bar_w * progress), bar_h)
            draw.rounded_rectangle(
                [bar_x, y_bar - bar_h // 2, bar_x + fill_w, y_bar + bar_h // 2],
                radius=bar_r, fill=RED + (255,)
            )

        # --- Remaining time ---
        draw.text((cx, y_remain), remain_str, font=remain_fnt, fill=WHITE, anchor="mm")

        return img.convert("RGB")
