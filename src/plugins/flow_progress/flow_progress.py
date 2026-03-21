from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageDraw
from utils.app_utils import get_font
import calendar
import logging
import unicodedata
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

PT_DAYS = ["SEGUNDA", "TERCA", "QUARTA", "QUINTA", "SEXTA", "SABADO", "DOMINGO"]
PT_MONTHS = [
    "JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO",
    "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO",
]


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
    if language == "pt":
        return [
            PT_DAYS[dt.weekday()],
            f"SEMANA {dt.isocalendar()[1]}",
            PT_MONTHS[dt.month - 1],
            str(dt.year),
        ]
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
    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        width, height = dimensions
        language = settings.get("language", "en")
        num_dots = int(settings.get("numDots", 15))
        corner_radius = int(settings.get("cornerRadius", 20))
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
            radius=corner_radius * scale,
            fill=CARD,
        )
        font = get_font("Dogica", 8, font_weight="bold") or get_font("Dogica", 8)
        if font is None:
            raise RuntimeError("Required font 'Dogica' not found.")
        pad_x = int(rw * 0.05)
        pad_y = int(rh * 0.10)
        content_h = rh - 2 * pad_y
        row_h = content_h / 4
        gap = rw * 0.025
        label_info = [text_to_dots(labels[i], font) for i in range(4)]
        pct_info = [text_to_dots(f"{pcts[i]}%", font) for i in range(4)]
        max_label_pw = max((d[1] for d in label_info), default=1) or 1
        max_pct_pw = max((d[1] for d in pct_info), default=1) or 1
        max_ph = max(
            max((d[2] for d in label_info), default=7),
            max((d[2] for d in pct_info), default=7),
        ) or 7
        h_spacing = (row_h * 0.42) / max_ph
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
        bar_dot_r = bar_dot_sp * 0.44
        for i in range(4):
            cy = pad_y + i * row_h + row_h / 2
            ty = cy - text_h / 2
            l_dots, _, _ = label_info[i]
            render_dots(draw, l_dots, pad_x, ty, dot_spacing, dot_radius, WHITE)
            filled = round(num_dots * pcts[i] / 100)
            for j in range(num_dots):
                cx = bar_start + j * bar_dot_sp + bar_dot_sp / 2
                c = WHITE if j < filled else DIM
                draw.ellipse(
                    [cx - bar_dot_r, cy - bar_dot_r, cx + bar_dot_r, cy + bar_dot_r],
                    fill=c,
                )
            p_dots, p_pw, _ = pct_info[i]
            px = rw - pad_x - p_pw * dot_spacing
            render_dots(draw, p_dots, px, ty, dot_spacing, dot_radius, WHITE)
        img = img.resize(dimensions, Image.LANCZOS)
        return img
