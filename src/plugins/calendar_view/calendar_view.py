import logging
import itertools
import pytz
from datetime import datetime
from utils.app_utils import get_font
from plugins.base_plugin.base_plugin import BasePlugin
from plugins.calendar_view.image_calendar import ImageCalendar, COLOR_PAIRS

logger = logging.getLogger(__name__)
DEFAULT_TIMEZONE = "US/Eastern"


class CalendarView(BasePlugin):
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
        cal = ImageCalendar(current_time)

        color_cycle = itertools.cycle(COLOR_PAIRS)
        for url in urls:
            cal.load_ical_url(url, next(color_cycle))

        cal.slash_past_days()
        cal.color_day(current_time.day, "lightblue")

        img = cal.render(
            dimensions,
            title_height=20,
            header_height=18,
            event_height=12,
            title_font=get_font("napoli", 20),
            header_font=get_font("napoli", 18),
            day_font=get_font("napoli", 12),
            event_font=get_font("jost", 12),
        )

        return img
