import logging
from datetime import datetime

import pytz
from PIL import Image, ImageColor, ImageDraw

from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import get_font

logger = logging.getLogger(__name__)

# Default colors
DEFAULT_PRIMARY = "#000000"
DEFAULT_SECONDARY = "#ffffff"
DEFAULT_PROGRESS_BAR = "#cc3232"

# Hardcoded locale data for Latin-script languages commonly used by the InkyPi
# community (hobbyists/tech in Europe and Americas). Jost font supports accented chars.
LOCALE_DATA = {
    "da": {
        "title": "I DAG",
        "days": ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"],
        "months_short": ["Jan", "Feb", "Mar", "Apr", "Maj", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dec"],
        "remaining": "tilbage",
    },
    "de": {
        "title": "HEUTE",
        "days": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
        "months_short": ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
        "remaining": "verbleibend",
    },
    "en": {
        "title": "TODAY",
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "months_short": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "remaining": "remaining",
    },
    "es": {
        "title": "HOY",
        "days": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
        "months_short": ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"],
        "remaining": "restantes",
    },
    "fr": {
        "title": "AUJOURD'HUI",
        "days": ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"],
        "months_short": ["Jan", "Fév", "Mar", "Avr", "Mai", "Jun", "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"],
        "remaining": "restant",
    },
    "it": {
        "title": "OGGI",
        "days": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"],
        "months_short": ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"],
        "remaining": "rimanenti",
    },
    "nb": {
        "title": "I DAG",
        "days": ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"],
        "months_short": ["Jan", "Feb", "Mar", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Des"],
        "remaining": "igjen",
    },
    "nl": {
        "title": "VANDAAG",
        "days": ["Maandag", "Dinsdag", "Woensdag", "Donderdag", "Vrijdag", "Zaterdag", "Zondag"],
        "months_short": ["Jan", "Feb", "Mrt", "Apr", "Mei", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dec"],
        "remaining": "resterend",
    },
    "pt": {
        "title": "HOJE",
        "days": ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"],
        "months_short": ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"],
        "remaining": "restantes",
    },
    "sv": {
        "title": "IDAG",
        "days": ["Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"],
        "months_short": ["Jan", "Feb", "Mar", "Apr", "Maj", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dec"],
        "remaining": "kvar",
    },
}


class Today(BasePlugin):
    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        tz_name = device_config.get_config("timezone") or "UTC"
        tz = pytz.timezone(tz_name)
        now = datetime.now(tz)

        time_format = device_config.get_config("time_format", default="12h")
        language = str(settings.get("language") or "en").strip().lower()
        locale = LOCALE_DATA.get(language, LOCALE_DATA["en"])

        primary_color = ImageColor.getcolor(settings.get("primaryColor") or DEFAULT_PRIMARY, "RGB")
        secondary_color = ImageColor.getcolor(settings.get("secondaryColor") or DEFAULT_SECONDARY, "RGB")
        progress_bar_color = ImageColor.getcolor(settings.get("progressBarColor") or DEFAULT_PROGRESS_BAR, "RGB")

        # Full day progress (00:00 to 23:59)
        total_day = 23 * 60 + 59
        cur = now.hour * 60 + now.minute
        progress = min(cur / total_day, 1.0)
        remaining = max(total_day - cur, 0)

        # Format time based on system time format setting
        if time_format == "24h":
            time_digits = f"{now.hour:02d}:{now.minute:02d}"
            period = ""
        else:
            hour = now.hour % 12 or 12
            period = "AM" if now.hour < 12 else "PM"
            time_digits = f"{hour}:{now.minute:02d}"

        # Date: WEEKDAY, MONTH_ABBR DAY
        day_name = locale["days"][now.weekday()].upper()
        month_abbr = locale["months_short"][now.month - 1].upper()
        date_str = f"{day_name}, {month_abbr} {now.day}"

        # Remaining time
        h, m = divmod(remaining, 60)
        remain_word = locale["remaining"]
        remain_str = f"{h}h {m:02d}m {remain_word}" if h > 0 else f"{m}m {remain_word}"

        return self._render(dimensions, locale["title"], time_digits, period, date_str, progress, remain_str,
                           primary_color, secondary_color, progress_bar_color)

    def _render(self, dimensions, title, time_digits, period, date_str, progress, remain_str,
                primary_color, secondary_color, progress_bar_color):
        w, h = dimensions

        # Derive helper colors from the user-chosen palette
        ghost_color = tuple(max(c - 25, 0) if c >= 128 else min(c + 25, 255) for c in primary_color)
        track_color = tuple(max(c - 50, 0) if c >= 128 else min(c + 50, 255) for c in primary_color)
        date_color = tuple((p + s) // 2 for p, s in zip(primary_color, secondary_color))

        img = Image.new("RGBA", (w, h), primary_color + (255,))
        draw = ImageDraw.Draw(img)

        # Flat card with rounded corners
        mx, my = int(w * 0.04), int(h * 0.04)
        cw, ch = w - 2 * mx, h - 2 * my
        radius = int(min(cw, ch) * 0.06)
        draw.rounded_rectangle([mx, my, mx + cw, my + ch], radius=radius, fill=primary_color)

        cx = w // 2
        dim = min(cw, ch)

        # Fonts — pushed slightly larger while preserving hierarchy
        title_fnt = get_font("Jost", int(dim * 0.09), "bold")
        date_fnt = get_font("Jost", int(dim * 0.10), "bold")
        remain_fnt = get_font("Jost", int(dim * 0.072))

        # Vertical layout positions
        y_title = my + int(ch * 0.075)
        y_clock = my + int(ch * 0.35)
        y_date = y_clock + int(ch * 0.30)
        y_bar = y_date + int(ch * 0.16)
        y_remain = y_bar + int(ch * 0.14)

        # --- Title label ---
        draw.text((cx, y_title), title, font=title_fnt, fill=secondary_color, anchor="mm")

        # --- Clock (auto-scale to fit card width) ---
        max_clock_w = cw * 0.90
        ghost = ''.join('8' if c.isdigit() else c for c in time_digits)
        clock_size = int(dim * 0.50)
        while clock_size > 16:
            clock_fnt = get_font("DS-Digital", clock_size)
            period_fnt = get_font("Jost", int(clock_size * 0.164), "bold")
            gap = int(dim * 0.015)
            test_w = draw.textlength(ghost, font=clock_fnt)
            if period:
                test_w += gap + draw.textlength(period, font=period_fnt)
            if test_w <= max_clock_w:
                break
            clock_size -= 2

        d_w = draw.textlength(time_digits, font=clock_fnt)
        if period:
            p_w = draw.textlength(period, font=period_fnt)
            total_w = d_w + gap + p_w
        else:
            total_w = d_w
        sx = cx - total_w / 2

        # Ghost digits (dim segments behind active digits)
        draw.text((sx, y_clock), ghost, font=clock_fnt, fill=ghost_color, anchor="lm")

        # Active time digits
        draw.text((sx, y_clock), time_digits, font=clock_fnt, fill=secondary_color, anchor="lm")

        # AM/PM — only rendered in 12h mode
        if period:
            draw.text((sx + d_w + gap, y_clock), period, font=period_fnt, fill=secondary_color, anchor="lm")

        # --- Date line ---
        draw.text((cx, y_date), date_str, font=date_fnt, fill=date_color, anchor="mm")

        # --- Progress bar ---
        bar_w = int(cw * 0.60)
        bar_h = int(dim * 0.04)
        bar_x = cx - bar_w // 2
        bar_r = bar_h // 2

        # Track
        draw.rounded_rectangle(
            [bar_x, y_bar - bar_h // 2, bar_x + bar_w, y_bar + bar_h // 2],
            radius=bar_r, fill=track_color + (255,)
        )

        # Fill
        if progress > 0:
            fill_w = max(int(bar_w * progress), bar_h)
            draw.rounded_rectangle(
                [bar_x, y_bar - bar_h // 2, bar_x + fill_w, y_bar + bar_h // 2],
                radius=bar_r, fill=progress_bar_color + (255,)
            )

        # --- Remaining time ---
        draw.text((cx, y_remain), remain_str, font=remain_fnt, fill=secondary_color, anchor="mm")

        return img.convert("RGB")
