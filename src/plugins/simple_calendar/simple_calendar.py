import calendar
import logging
import unicodedata
from datetime import datetime

import pytz
from PIL import Image, ImageColor, ImageDraw

from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import get_font

logger = logging.getLogger(__name__)

LOCALE_DATA = {
    "de": {
        "weekday_abbrev": ["MON", "DIE", "MIT", "DON", "FRE", "SAM", "SON"],
        "headers": ["S", "M", "D", "M", "D", "F", "S"],
        "months": ["JANUAR", "FEBRUAR", "MÄRZ", "APRIL", "MAI", "JUNI", "JULI", "AUGUST", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DEZEMBER"],
    },
    "en": {
        "weekday_abbrev": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"],
        "headers": ["S", "M", "T", "W", "T", "F", "S"],
        "months": ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"],
    },
    "es": {
        "weekday_abbrev": ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"],
        "headers": ["D", "L", "M", "M", "J", "V", "S"],
        "months": ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"],
    },
    "fr": {
        "weekday_abbrev": ["LUN", "MAR", "MER", "JEU", "VEN", "SAM", "DIM"],
        "headers": ["D", "L", "M", "M", "J", "V", "S"],
        "months": ["JANVIER", "FÉVRIER", "MARS", "AVRIL", "MAI", "JUIN", "JUILLET", "AOÛT", "SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DÉCEMBRE"],
    },
    "id": {
        "weekday_abbrev": ["SEN", "SEL", "RAB", "KAM", "JUM", "SAB", "MIN"],
        "headers": ["M", "S", "S", "R", "K", "J", "S"],
        "months": ["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI", "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"],
    },
    "it": {
        "weekday_abbrev": ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"],
        "headers": ["D", "L", "M", "M", "G", "V", "S"],
        "months": ["GENNAIO", "FEBBRAIO", "MARZO", "APRILE", "MAGGIO", "GIUGNO", "LUGLIO", "AGOSTO", "SETTEMBRE", "OTTOBRE", "NOVEMBRE", "DICEMBRE"],
    },
    "nl": {
        "weekday_abbrev": ["MAA", "DIN", "WOE", "DON", "VRI", "ZAT", "ZON"],
        "headers": ["Z", "M", "D", "W", "D", "V", "Z"],
        "months": ["JANUARI", "FEBRUARI", "MAART", "APRIL", "MEI", "JUNI", "JULI", "AUGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DECEMBER"],
    },
    "pt": {
        "weekday_abbrev": ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"],
        "headers": ["D", "S", "T", "Q", "Q", "S", "S"],
        "months": ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"],
    },
}

# ---------------------------------------------------------------------------
# Dot-matrix glyph definitions (5 wide × 7 tall for digits, variable for letters)
# Each glyph is a list of (row, col) positions where a dot should be drawn.
# ---------------------------------------------------------------------------

_DIGIT_W, _DIGIT_H = 5, 7

_DIGIT_PATTERNS = {
    "0": [
        "01110",
        "10001",
        "10011",
        "10101",
        "11001",
        "10001",
        "01110",
    ],
    "1": [
        "00100",
        "01100",
        "00100",
        "00100",
        "00100",
        "00100",
        "01110",
    ],
    "2": [
        "01110",
        "10001",
        "00001",
        "00110",
        "01000",
        "10000",
        "11111",
    ],
    "3": [
        "01110",
        "10001",
        "00001",
        "00110",
        "00001",
        "10001",
        "01110",
    ],
    "4": [
        "00010",
        "00110",
        "01010",
        "10010",
        "11111",
        "00010",
        "00010",
    ],
    "5": [
        "11111",
        "10000",
        "11110",
        "00001",
        "00001",
        "10001",
        "01110",
    ],
    "6": [
        "01110",
        "10001",
        "10000",
        "11110",
        "10001",
        "10001",
        "01110",
    ],
    "7": [
        "11111",
        "00001",
        "00010",
        "00100",
        "01000",
        "01000",
        "01000",
    ],
    "8": [
        "01110",
        "10001",
        "10001",
        "01110",
        "10001",
        "10001",
        "01110",
    ],
    "9": [
        "01110",
        "10001",
        "10001",
        "01111",
        "00001",
        "10001",
        "01110",
    ],
}

# 3×5 compact letter patterns for weekday abbreviations
_LETTER_W, _LETTER_H = 5, 7

_LETTER_PATTERNS = {
    "S": [
        "01110",
        "10001",
        "10000",
        "01110",
        "00001",
        "10001",
        "01110",
    ],
    "A": [
        "01110",
        "10001",
        "10001",
        "11111",
        "10001",
        "10001",
        "10001",
    ],
    "T": [
        "11111",
        "00100",
        "00100",
        "00100",
        "00100",
        "00100",
        "00100",
    ],
    "M": [
        "10001",
        "11011",
        "10101",
        "10101",
        "10001",
        "10001",
        "10001",
    ],
    "O": [
        "01110",
        "10001",
        "10001",
        "10001",
        "10001",
        "10001",
        "01110",
    ],
    "N": [
        "10001",
        "11001",
        "10101",
        "10011",
        "10001",
        "10001",
        "10001",
    ],
    "U": [
        "10001",
        "10001",
        "10001",
        "10001",
        "10001",
        "10001",
        "01110",
    ],
    "E": [
        "11111",
        "10000",
        "10000",
        "11110",
        "10000",
        "10000",
        "11111",
    ],
    "W": [
        "10001",
        "10001",
        "10001",
        "10101",
        "10101",
        "11011",
        "10001",
    ],
    "D": [
        "11100",
        "10010",
        "10001",
        "10001",
        "10001",
        "10010",
        "11100",
    ],
    "H": [
        "10001",
        "10001",
        "10001",
        "11111",
        "10001",
        "10001",
        "10001",
    ],
    "F": [
        "11111",
        "10000",
        "10000",
        "11110",
        "10000",
        "10000",
        "10000",
    ],
    "R": [
        "11110",
        "10001",
        "10001",
        "11110",
        "10010",
        "10001",
        "10001",
    ],
    "I": [
        "01110",
        "00100",
        "00100",
        "00100",
        "00100",
        "00100",
        "01110",
    ],
    "P": [
        "11110",
        "10001",
        "10001",
        "11110",
        "10000",
        "10000",
        "10000",
    ],
    "Q": [
        "01110",
        "10001",
        "10001",
        "10001",
        "10001",
        "10011",
        "01111",
    ],
    "B": [
        "11110",
        "10001",
        "10001",
        "11110",
        "10001",
        "10001",
        "11110",
    ],
    "G": [
        "01110",
        "10001",
        "10000",
        "10111",
        "10001",
        "10001",
        "01110",
    ],
    "J": [
        "00111",
        "00010",
        "00010",
        "00010",
        "00010",
        "10010",
        "01100",
    ],
    "K": [
        "10001",
        "10010",
        "10100",
        "11000",
        "10100",
        "10010",
        "10001",
    ],
    "L": [
        "10000",
        "10000",
        "10000",
        "10000",
        "10000",
        "10000",
        "11111",
    ],
    "V": [
        "10001",
        "10001",
        "10001",
        "10001",
        "10001",
        "01010",
        "00100",
    ],
    "X": [
        "10001",
        "10001",
        "01010",
        "00100",
        "01010",
        "10001",
        "10001",
    ],
    "Z": [
        "11111",
        "00001",
        "00010",
        "00100",
        "01000",
        "10000",
        "11111",
    ],
}


def _get_dot_positions(char):
    """Return list of (row, col) positions for a character glyph."""
    patterns = _DIGIT_PATTERNS if char.isdigit() else _LETTER_PATTERNS
    rows = patterns.get(char.upper(), [])
    positions = []
    for r, row_str in enumerate(rows):
        for c, ch in enumerate(row_str):
            if ch == "1":
                positions.append((r, c))
    return positions


def _draw_dotmatrix_text(draw, text, center_x, center_y, dot_radius, dot_spacing,
                         fill, glyph_w=5, glyph_h=7, char_gap_dots=1.5):
    """Draw a string of dot-matrix characters centred at (center_x, center_y)."""

    cell = dot_radius * 2 + dot_spacing
    char_width_px = glyph_w * cell
    gap_px = char_gap_dots * cell
    total_width = len(text) * char_width_px + (len(text) - 1) * gap_px
    total_height = glyph_h * cell

    start_x = center_x - total_width / 2
    start_y = center_y - total_height / 2

    for i, ch in enumerate(text):
        ox = start_x + i * (char_width_px + gap_px)
        oy = start_y
        for r, c in _get_dot_positions(ch):
            cx = ox + c * cell + dot_radius
            cy = oy + r * cell + dot_radius
            draw.ellipse(
                [cx - dot_radius, cy - dot_radius,
                 cx + dot_radius, cy + dot_radius],
                fill=fill,
            )


class SimpleCalendar(BasePlugin):

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = False
        return template_params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        timezone_name = device_config.get_config("timezone", default="America/New_York")
        tz = pytz.timezone(timezone_name)
        selected_date = self._get_selected_date(settings, tz)
        language = self._get_locale_key(settings.get("locale") or settings.get("language", "en"))
        locale_data = LOCALE_DATA.get(language)

        primary_color = self._parse_color(settings.get("primaryColor"), (230, 26, 26))
        highlight_color = self._parse_color(settings.get("highlightColor"), (163, 13, 13))

        return self._render_calendar(dimensions, selected_date, primary_color, highlight_color, locale_data, language)

    # ------------------------------------------------------------------
    # Core rendering
    # ------------------------------------------------------------------

    def _render_calendar(self, dimensions, now, primary_color, highlight_color, locale_data, language):
        W, H = dimensions

        # Colours
        dark = primary_color
        light_bg = (245, 245, 245)
        white = (255, 255, 255)
        mid_gray = (178, 178, 178)
        text_color = (56, 56, 56)

        img = Image.new("RGB", (W, H), white)
        draw = ImageDraw.Draw(img)

        # Card geometry — generous margin, large rounded card
        margin_x = int(W * 0.04)
        margin_y = int(H * 0.06)
        card_left = margin_x
        card_top = margin_y
        card_right = W - margin_x
        card_bottom = H - margin_y
        card_w = card_right - card_left
        card_h = card_bottom - card_top
        corner_r = int(min(card_w, card_h) * 0.06)

        # Draw the full card background (light)
        draw.rounded_rectangle(
            [card_left, card_top, card_right, card_bottom],
            radius=corner_r,
            fill=light_bg,
        )

        # Left panel: dark block covering ~40% width (narrower in portrait)
        aspect = card_w / max(card_h, 1)
        left_ratio = 0.38 if aspect >= 1.0 else 0.30
        left_panel_w = int(card_w * left_ratio)
        left_right_edge = card_left + left_panel_w

        # Draw dark left panel with rounded corners only on left side
        # We draw a full rounded rect then cover the right corners with a plain rect
        draw.rounded_rectangle(
            [card_left, card_top, left_right_edge + corner_r, card_bottom],
            radius=corner_r,
            fill=dark,
        )
        # Cover the right rounded corners to make them sharp
        draw.rectangle(
            [left_right_edge, card_top, left_right_edge + corner_r, card_bottom],
            fill=dark,
        )

        # Clean edge: redraw light bg over the overlap area on the right side
        draw.rectangle(
            [left_right_edge, card_top, left_right_edge + 1, card_bottom],
            fill=dark,
        )

        # === LEFT PANEL CONTENT (dot-matrix day + weekday) ===
        left_cx = card_left + left_panel_w // 2
        left_cy = card_top + card_h // 2

        day_str = str(now.day)
        weekday_str = self._get_weekday_abbrev(now, locale_data, language)

        # Scale dots relative to card height for consistent sizing
        ref = min(card_h, left_panel_w)

        # Day number — large dots
        day_dot_r = max(int(ref * 0.024), 2)
        day_dot_spacing = max(int(ref * 0.014), 1)

        # Weekday — smaller dots
        wk_dot_r = max(int(ref * 0.013), 1)
        wk_dot_spacing = max(int(ref * 0.008), 1)

        # Vertical arrangement: day number above centre, weekday below
        day_cell = day_dot_r * 2 + day_dot_spacing
        wk_cell = wk_dot_r * 2 + wk_dot_spacing
        day_block_h = _DIGIT_H * day_cell
        wk_block_h = _LETTER_H * wk_cell
        gap = int(ref * 0.08)
        total_content_h = day_block_h + gap + wk_block_h
        content_top = left_cy - total_content_h // 2

        day_center_y = content_top + day_block_h // 2
        wk_center_y = content_top + day_block_h + gap + wk_block_h // 2

        _draw_dotmatrix_text(
            draw, day_str, left_cx, day_center_y,
            day_dot_r, day_dot_spacing, white,
            glyph_w=_DIGIT_W, glyph_h=_DIGIT_H,
        )
        _draw_dotmatrix_text(
            draw, weekday_str, left_cx, wk_center_y,
            wk_dot_r, wk_dot_spacing, white,
            glyph_w=_LETTER_W, glyph_h=_LETTER_H,
            char_gap_dots=1.2,
        )

        # === RIGHT PANEL CONTENT (month name, weekday headers, day grid) ===
        right_left = left_right_edge
        right_w = card_right - right_left
        right_cx = right_left + right_w // 2

        # Font sizes scaled to available column width to prevent overlap
        grid_side_pad = int(right_w * 0.08)
        grid_left = right_left + grid_side_pad
        grid_right_edge = card_right - grid_side_pad
        grid_w = grid_right_edge - grid_left
        col_w = grid_w / 7

        # Scale fonts proportionally to column width (fits 2-digit numbers)
        month_font_size = max(int(col_w * 0.72), 12)
        year_font_size = max(int(col_w * 0.46), 10)
        header_font_size = max(int(col_w * 0.42), 10)
        day_font_size = max(int(col_w * 0.42), 10)

        month_font = get_font("Jost", month_font_size, "bold")
        year_font = get_font("Jost", year_font_size)
        header_font = get_font("Jost", header_font_size)
        day_font = get_font("Jost", day_font_size)

        # Layout vertical positions
        top_pad = int(card_h * 0.08)
        month_y = card_top + top_pad

        # Month and year
        month_name = self._get_month_name(now, locale_data, language)
        year_text = str(now.year)
        month_bbox = draw.textbbox((0, 0), month_name, font=month_font)
        year_bbox = draw.textbbox((0, 0), year_text, font=year_font)
        month_width = month_bbox[2] - month_bbox[0]
        year_width = year_bbox[2] - year_bbox[0]
        header_gap = max(int(col_w * 0.5), 10)
        total_width = month_width + header_gap + year_width
        header_left = right_cx - total_width / 2

        # Baseline anchoring: accented glyphs (É, Ä) extend upward
        # without shifting letter positions or downstream layout.
        baseline_y = month_y + month_font.getmetrics()[0]
        title_lift = max(int(month_font_size * 0.30), 8)

        draw.text(
            (header_left, baseline_y - title_lift), month_name,
            fill=text_color, font=month_font, anchor="ls",
        )
        year_y = baseline_y - int(month_font_size * 0.15) - title_lift
        draw.text(
            (header_left + month_width + header_gap, year_y),
            year_text,
            fill=(138, 138, 138), font=year_font, anchor="ls",
        )

        # Weekday header row
        header_labels = self._get_weekday_headers(locale_data, language)
        header_y = month_y + int(month_font_size * 1.6)

        for i, label in enumerate(header_labels):
            x = grid_left + col_w * i + col_w / 2
            draw.text(
                (x, header_y), label,
                fill=mid_gray, font=header_font, anchor="mt",
            )

        # Month day grid
        grid_top_y = header_y + int(header_font_size * 2.0)
        available_grid_h = card_bottom - grid_top_y - int(card_h * 0.04)

        cal = calendar.Calendar(firstweekday=6).monthdayscalendar(now.year, now.month)
        num_weeks = len(cal)
        row_h = available_grid_h / num_weeks

        today_circle_r = int(min(col_w, row_h) * 0.43)

        for week_idx, week in enumerate(cal):
            row_cy = grid_top_y + row_h * week_idx + row_h / 2
            for dow, day in enumerate(week):
                if day == 0:
                    continue
                col_cx = grid_left + col_w * dow + col_w / 2

                if day == now.day:
                    # Today highlight: filled circle using the configured accent color
                    draw.ellipse(
                        [col_cx - today_circle_r, row_cy - today_circle_r,
                         col_cx + today_circle_r, row_cy + today_circle_r],
                        fill=highlight_color,
                    )
                    draw.text(
                        (col_cx, row_cy), str(day),
                        fill=white, font=day_font, anchor="mm",
                    )
                else:
                    draw.text(
                        (col_cx, row_cy), str(day),
                        fill=text_color, font=day_font, anchor="mm",
                    )

        return img

    @staticmethod
    def _get_selected_date(settings, tz):
        custom_date = settings.get("customDate")
        if custom_date:
            return datetime.strptime(custom_date, "%Y-%m-%d").date()

        return datetime.now(tz).date()

    @staticmethod
    def _get_locale_key(language):
        language = str(language or "en").strip().lower()
        return language if language in LOCALE_DATA else "en"

    @staticmethod
    def _strip_accents(text):
        normalized = unicodedata.normalize("NFKD", text)
        return "".join(char for char in normalized if not unicodedata.combining(char))

    def _get_weekday_abbrev(self, now, locale_data, language):
        if locale_data:
            return self._strip_accents(locale_data["weekday_abbrev"][now.weekday()]).upper()
        return self._strip_accents(now.strftime("%a").upper())[:3]

    def _get_month_name(self, now, locale_data, language):
        if locale_data:
            return locale_data["months"][now.month - 1]
        return self._strip_accents(now.strftime("%B").upper())

    def _get_weekday_headers(self, locale_data, language):
        if locale_data:
            return locale_data["headers"]
        return ["S", "M", "T", "W", "T", "F", "S"]

    @staticmethod
    def _parse_color(value, fallback):
        if not value:
            return fallback

        try:
            return ImageColor.getrgb(value)
        except Exception:
            return fallback
