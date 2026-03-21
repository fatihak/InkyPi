from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageDraw
from utils.app_utils import get_font
import calendar
import logging
import unicodedata
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

DEFAULT_NUM_BARS = 2
DEFAULT_NUM_DOTS = 20
FIXED_CORNER_RADIUS = 20

# Hardcoded locale data for languages that render cleanly in Dogica (ASCII-only pixel font).
# All text must be accent-free uppercase. Languages where accent-stripping produces
# unrecognisable words (e.g. Polish, Turkish) are intentionally excluded.
LOCALE_DATA = {
    "de": {
        "days": ["MONTAG", "DIENSTAG", "MITTWOCH", "DONNERSTAG", "FREITAG", "SAMSTAG", "SONNTAG"],
        "months": ["JANUAR", "FEBRUAR", "MARZ", "APRIL", "MAI", "JUNI",
                   "JULI", "AUGUST", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DEZEMBER"],
        "week": "WOCHE",
    },
    "en": None,  # English uses strftime directly
    "es": {
        "days": ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"],
        "months": ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
                   "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"],
        "week": "SEMANA",
    },
    "fr": {
        "days": ["LUNDI", "MARDI", "MERCREDI", "JEUDI", "VENDREDI", "SAMEDI", "DIMANCHE"],
        "months": ["JANVIER", "FEVRIER", "MARS", "AVRIL", "MAI", "JUIN",
                   "JUILLET", "AOUT", "SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DECEMBRE"],
        "week": "SEMAINE",
    },
    "id": {
        "days": ["SENIN", "SELASA", "RABU", "KAMIS", "JUMAT", "SABTU", "MINGGU"],
        "months": ["JANUARI", "FEBRUARI", "MARET", "APRIL", "MEI", "JUNI",
                   "JULI", "AGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DESEMBER"],
        "week": "MINGGU KE",
    },
    "it": {
        "days": ["LUNEDI", "MARTEDI", "MERCOLEDI", "GIOVEDI", "VENERDI", "SABATO", "DOMENICA"],
        "months": ["GENNAIO", "FEBBRAIO", "MARZO", "APRILE", "MAGGIO", "GIUGNO",
                   "LUGLIO", "AGOSTO", "SETTEMBRE", "OTTOBRE", "NOVEMBRE", "DICEMBRE"],
        "week": "SETTIMANA",
    },
    "nl": {
        "days": ["MAANDAG", "DINSDAG", "WOENSDAG", "DONDERDAG", "VRIJDAG", "ZATERDAG", "ZONDAG"],
        "months": ["JANUARI", "FEBRUARI", "MAART", "APRIL", "MEI", "JUNI",
                   "JULI", "AUGUSTUS", "SEPTEMBER", "OKTOBER", "NOVEMBER", "DECEMBER"],
        "week": "WEEK",
    },
    "pt": {
        "days": ["SEGUNDA", "TERCA", "QUARTA", "QUINTA", "SEXTA", "SABADO", "DOMINGO"],
        "months": ["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO",
                   "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"],
        "week": "SEMANA",
    },
}


def calc_day_progress(dt):
    elapsed = dt.hour * 3600 + dt.minute * 60 + dt.second
    return min(round(elapsed / 86400 * 100), 100)

def calc_week_progress(dt):
    elapsed = dt.weekday() * 86400 + dt.hour * 3600 + dt.minute * 60 + dt.second
    return min(round(elapsed / (7 * 86400) * 100), 100)

def calc_month_progress(dt):
    days_in_month = calendar.monthrange(dt.year, dt.month)[1]
    elapsed = (dt.day - 1) + (dt.hour * 3600 + dt.minute * 60 + dt.second) / 86400
    return min(round(elapsed / days_in_month * 100), 100)

def calc_year_progress(dt):
    start = datetime(dt.year, 1, 1, tzinfo=dt.tzinfo)
    end = datetime(dt.year + 1, 1, 1, tzinfo=dt.tzinfo)
    total = (end - start).total_seconds()
    elapsed = (dt - start).total_seconds()
    return min(round(elapsed / total * 100), 100)

def get_labels(dt, language):
    locale = LOCALE_DATA.get(language)
    if locale:
        return [
            locale["days"][dt.weekday()],
            f"{locale['week']} {dt.isocalendar()[1]}",
            locale["months"][dt.month - 1],
            str(dt.year),
        ]
    # English (default) — use strftime with accent stripping as safety net
    return [
        _strip_accents(dt.strftime("%A").upper()),
        f"WEEK {dt.isocalendar()[1]}",
        _strip_accents(dt.strftime("%B").upper()),
        str(dt.year),
    ]

def _strip_accents(text):
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))

def text_to_dots(text, font):
    buf_w = max(len(text) * 20, 200)
    temp = Image.new("L", (buf_w, 50), 0)
    ImageDraw.Draw(temp).text((1, 1), text, font=font, fill=255)
    bbox = temp.getbbox()
    if not bbox:
        return [], 0, 0
    cropped = temp.crop(bbox)
    w, h = cropped.size
    px = cropped.load()
    dots = [(x, y) for y in range(h) for x in range(w) if px[x, y] > 128]
    return dots, w, h

def render_dots(draw, dots, x, y, spacing, radius, color):
    for dx, dy in dots:
        cx = x + dx * spacing
        cy = y + dy * spacing
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=color,
        )

class FlowProgress(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = False
        return template_params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        
        width, height = dimensions
        
        # Safely extract and validate settings
        language = str(settings.get("language", "en")).strip() or "en"
        
        try:
            num_dots = int(settings.get("numDots", DEFAULT_NUM_DOTS))
            num_dots = max(5, min(40, num_dots))
        except (TypeError, ValueError):
            num_dots = DEFAULT_NUM_DOTS
        
        try:
            num_bars = int(settings.get("numBars", DEFAULT_NUM_BARS))
            num_bars = max(1, min(3, num_bars))
        except (TypeError, ValueError):
            num_bars = DEFAULT_NUM_BARS
        
        tz_name = device_config.get_config("timezone", default="America/New_York")
        tz = pytz.timezone(tz_name)
        now = datetime.now(tz)
        labels = get_labels(now, language)
        pcts = [
            calc_day_progress(now),
            calc_week_progress(now),
            calc_month_progress(now),
            calc_year_progress(now),
        ]
        scale = 2
        rw, rh = width * scale, height * scale
        BG = (0, 0, 0)
        CARD = (18, 18, 18)
        WHITE = (255, 255, 255)
        DIM = (65, 65, 65)
        img = Image.new("RGB", (rw, rh), BG)
        draw = ImageDraw.Draw(img)
        m = int(min(rw, rh) * 0.03)
        draw.rounded_rectangle(
            [m, m, rw - m, rh - m],
            radius=FIXED_CORNER_RADIUS * scale,
            fill=CARD,
        )
        font = get_font("Dogica", 8, font_weight="bold") or get_font("Dogica", 8)
        if font is None:
            raise RuntimeError("Required font 'Dogica' not found.")
        pad_x = int(rw * 0.05)
        pad_y = int(rh * 0.10)
        content_h = rh - 2 * pad_y
        item_count = len(labels)
        row_h = content_h / item_count
        gap = rw * 0.025
        label_info = [text_to_dots(label, font) for label in labels]
        pct_info = [text_to_dots(f"{pct}%", font) for pct in pcts]
        max_label_pw = max((d[1] for d in label_info), default=1) or 1
        max_pct_pw = max((d[1] for d in pct_info), default=1) or 1
        max_ph = max(
            max((d[2] for d in label_info), default=7),
            max((d[2] for d in pct_info), default=7),
        ) or 7
        bar_block_h = row_h * 0.34
        bar_gap = max(row_h * 0.06, 4.0)
        available_bar_h = max(bar_block_h - bar_gap * (num_bars - 1), row_h * 0.14)
        single_bar_h = available_bar_h / num_bars
        h_spacing = (row_h * 0.30) / max_ph
        min_bar_w = rw * 0.30
        w_spacing = (rw - 2 * pad_x - min_bar_w - 2 * gap) / (max_label_pw + max_pct_pw)
        dot_spacing = max(min(h_spacing, w_spacing), 3.0)
        dot_radius = max(dot_spacing * 0.42, 1.5)
        max_lw = max_label_pw * dot_spacing
        max_pw = max_pct_pw * dot_spacing
        text_h = max_ph * dot_spacing
        bar_start = pad_x + max_lw + gap
        bar_end = rw - pad_x - max_pw - gap
        bar_width = bar_end - bar_start
        bar_dot_sp = bar_width / max(num_dots, 1)
        bar_dot_r = min(bar_dot_sp * 0.32, single_bar_h * 0.45)
        for i in range(item_count):
            cy = pad_y + i * row_h + row_h / 2
            ty = cy - text_h / 2
            l_dots, _, _ = label_info[i]
            render_dots(draw, l_dots, pad_x, ty, dot_spacing, dot_radius, WHITE)
            filled = round(num_dots * pcts[i] / 100)
            bars_total_h = num_bars * (bar_dot_r * 2) + (num_bars - 1) * bar_gap
            top_y = cy - bars_total_h / 2 + bar_dot_r
            for bar_index in range(num_bars):
                bar_y = top_y + bar_index * (bar_dot_r * 2 + bar_gap)
                for j in range(num_dots):
                    cx = bar_start + j * bar_dot_sp + bar_dot_sp / 2
                    c = WHITE if j < filled else DIM
                    draw.ellipse(
                        [cx - bar_dot_r, bar_y - bar_dot_r, cx + bar_dot_r, bar_y + bar_dot_r],
                        fill=c,
                    )
            p_dots, p_pw, _ = pct_info[i]
            px = rw - pad_x - p_pw * dot_spacing
            render_dots(draw, p_dots, px, ty, dot_spacing, dot_radius, WHITE)
        img = img.resize(dimensions, Image.LANCZOS)
        return img
