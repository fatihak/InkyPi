import logging
import requests
import itertools
import calendar
import icalendar
import recurring_ical_events
import pytz
from datetime import datetime, timedelta
from PIL import Image, ImageDraw
from utils.app_utils import get_font
from plugins.base_plugin.base_plugin import BasePlugin
from plugins.calendar.image_calendar import ImageCalendar

logger = logging.getLogger(__name__)
DEFAULT_TIMEZONE = "US/Eastern"

COLOR_PAIRS = [
    ("white", "deepskyblue"),
    ("black", "chartreuse"),
    ("white", "deeppink"),
    ("black", "orange"),
    ("white", "blue"),
    ("white", "forestgreen"),
    ("white", "chocolate"),
    ("white", "red"),
    ("black", "lime"),
    ("black", "yellow"),
]


class Calendar(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params["timezones"] = sorted(pytz.all_timezones_set)
        template_params["inputUrls"] = ""
        return template_params

    def generate_image(self, settings, device_config):
        timezone_name = settings.get("timezoneName", DEFAULT_TIMEZONE)
        tz = pytz.timezone(timezone_name)

        urls = settings.get("inputUrls", "").splitlines()

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        current_time = datetime.now(tz)
        range_start = current_time.replace(day=1, hour=0, minute=0, second=0)
        _, last_day = calendar.monthrange(current_time.year, current_time.month)
        range_end = current_time.replace(day=last_day, hour=23, minute=59, second=59)

        cal = ImageCalendar(current_time.year, current_time.month)

        color_cycle = itertools.cycle(COLOR_PAIRS)
        for url in urls:
            ical = self.fetch_calendar_from_url(url)
            if ical:
                events = recurring_ical_events.of(ical).between(range_start, range_end)
                text_color, background_color = next(color_cycle)
                for event in events:
                    start = event["DTSTART"].dt
                    end = event["DTEND"].dt
                    summary = event["SUMMARY"]
                    if isinstance(start, datetime):
                        time = start.strftime("%H:%M").strip()
                        cal.add_event(
                            start.day,
                            summary,
                            time=time,
                            color=text_color,
                            background=background_color,
                        )
                    else:
                        cal.add_event(
                            start.day,
                            summary,
                            color=text_color,
                            background=background_color,
                        )
                        next_day = max(start, range_start.date()) + timedelta(days=1)
                        last = (
                            min(end, range_end).date()
                            if isinstance(end, datetime)
                            else min(end, range_end.date())
                        )
                        while next_day < last:
                            cal.add_event(
                                next_day.day,
                                summary,
                                color=text_color,
                                background=background_color,
                            )
                            next_day += timedelta(days=1)

        dt = range_start
        while dt.day < current_time.day:
            cal.slash_day(dt.day, direction="down" if dt.day % 2 == 0 else "up")
            dt += timedelta(days=1)

        cal.color_day(current_time.day, "lightblue")
        img = cal.render(
            dimensions,
            header_height=18,
            event_height=12,
            header_font=get_font("napoli", 18),
            day_font=get_font("napoli", 12),
            event_font=get_font("jost", 12),
        )

        text = Image.new("RGBA", dimensions, (0, 0, 0, 0))
        font_size = 20
        fnt = get_font("napoli", font_size)
        text_draw = ImageDraw.Draw(text)

        w, h = dimensions
        time_str = current_time.strftime("%H:%M")
        month_str = calendar.TextCalendar().formatmonthname(
            current_time.year, current_time.month, w, withyear=True
        )
        text_draw.text(
            (10, h - font_size),
            time_str,
            font=fnt,
            anchor="lt",
            fill=(0, 0, 0) + (255,),
        )
        text_draw.text(
            (w - 10, h - font_size),
            month_str.strip(),
            font=fnt,
            anchor="rt",
            fill=(0, 0, 0) + (255,),
        )

        combined = Image.alpha_composite(img, text)
        return combined

    @staticmethod
    def fetch_calendar_from_url(url):
        try:
            response = requests.get(url)
            response.raise_for_status()
            return icalendar.Calendar.from_ical(response.text)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching calendar from {url}: {e}")
            return None
