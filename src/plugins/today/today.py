from plugins.base_plugin.base_plugin import BasePlugin
from plugins.today.constants import FONT_SIZES, LOCALE_MAP
from PIL import Image, ImageColor
import icalendar
import recurring_ical_events
from io import BytesIO
import requests
import logging
from datetime import datetime, timedelta
import pytz
import html
from babel.dates import format_date


logger = logging.getLogger(__name__)

class Today(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        template_params['locale_map'] = LOCALE_MAP
        return template_params

    def generate_image(self, settings, device_config):
        calendar_urls = settings.get('calendarURLs[]')
        calendar_colors = settings.get('calendarColors[]')

        if not calendar_urls:
            raise RuntimeError("At least one calendar URL is required")
        for url in calendar_urls:
            if not url.strip():
                raise RuntimeError("Invalid calendar URL")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        timezone = device_config.get_config("timezone", default="America/New_York")
        tz = pytz.timezone(timezone)

        current_dt = datetime.now(tz)
        start = datetime(current_dt.year, current_dt.month, current_dt.day)
        end = start + timedelta(days=1)
        logger.debug(f"Fetching events for {start} --> [{current_dt}] --> {end}")
        events = self.fetch_ics_events(calendar_urls, calendar_colors, tz, start, end)
        events.sort(key=lambda e: e.get('dtstart', ''))
        if not events:
            logger.warning("No events found for ics url")

        language = settings.get('language', 'en')
        day_of_week = format_date(current_dt, 'EEEE', locale=language)
        today = format_date(current_dt, 'long', locale=language)

        template_params = {
            "events": events[:10],
            "current_dt": current_dt.replace(minute=0, second=0, microsecond=0).isoformat(),
            "timezone": timezone,
            "plugin_settings": settings,
            "font_scale": FONT_SIZES.get(settings.get('fontSize', 'normal'), 1),
            "day_of_week": day_of_week,
            "today": today
        }

        image = self.render_image(dimensions, "today.html", "today.css", template_params)
        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")
        return image

    def fetch_ics_events(self, calendar_urls, colors, tz, start_range, end_range):
        parsed_events = []

        for calendar_url, color in zip(calendar_urls, colors):
            cal = self.fetch_calendar(calendar_url)
            events = recurring_ical_events.of(cal).between(start_range, end_range)
            contrast_color = self.get_contrast_color(color)

            for event in events:
                start, end, all_day = self.parse_data_points(event, tz)
                parsed_event = {
                    "title": html.unescape(event.get("summary")),
                    "description": html.unescape(event.get("description", "")),
                    "start": start,
                    "backgroundColor": color,
                    "textColor": contrast_color,
                    "allDay": all_day
                }
                if end:
                    parsed_event['end'] = end

                parsed_events.append(parsed_event)

        return parsed_events

    def parse_data_points(self, event, tz):
        all_day = False
        dtstart = event.decoded("dtstart")
        if isinstance(dtstart, datetime):
            start = dtstart.astimezone(tz).isoformat()
        else:
            start = dtstart.isoformat()
            all_day = True

        end = None
        if "dtend" in event:
            dtend = event.decoded("dtend")
            if isinstance(dtend, datetime):
                end = dtend.astimezone(tz).isoformat()
            else:
                end = dtend.isoformat()
        elif "duration" in event:
            duration = event.decoded("duration")
            dtend = dtstart + duration
            if isinstance(dtend, datetime):
                end = dtend.astimezone(tz).isoformat()
            else:
                end = dtend.isoformat()
        return start, end, all_day

    def fetch_calendar(self, calendar_url):
        try:
            response = requests.get(calendar_url, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'  # Ensure UTF-8 encoding
            calendar_data = response.text
            return icalendar.Calendar.from_ical(calendar_data)
        except Exception as e:
            raise RuntimeError(f"Failed to fetch iCalendar url: {str(e)}")

    def get_contrast_color(self, color):
        """
        Returns '#000000' (black) or '#ffffff' (white) depending on the contrast
        against the given color.
        """
        r, g, b = ImageColor.getrgb(color)
        # YIQ formula to estimate brightness
        yiq = (r * 299 + g * 587 + b * 114) / 1000

        return '#000000' if yiq >= 150 else '#ffffff'
