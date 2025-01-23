import logging
import itertools
import pytz
from timezonefinder import TimezoneFinder
from astral.sun import sun
from astral import LocationInfo
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
        latitude = float(settings.get("latitude", 0))
        longitude = float(settings.get("longitude", 0))
        tzName = TimezoneFinder().timezone_at(lat=latitude, lng=longitude)
        tz = pytz.timezone(tzName)

        urls = settings.get("inputUrls", "").splitlines()

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        current_time = datetime.now(tz)
        cal = ImageCalendar(current_time)

        location_info = LocationInfo(timezone=tz, latitude=latitude, longitude=longitude)
        sun_info = sun(location_info.observer, date=current_time)

        color_cycle = itertools.cycle(COLOR_PAIRS)
        for url in urls:
            cal.load_ical_url(url, next(color_cycle))

        if settings.get("slash_past_days", "off") == "on":
            cal.slash_past_days()
        if settings.get("highlight_today", "off") == "on":
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
            sunrise=sun_info["sunrise"],
            noon=sun_info["noon"],
            sunset=sun_info["sunset"],
        )

        return img
