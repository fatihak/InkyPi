import os
from utils.app_utils import resolve_path, get_font
from plugins.base_plugin.base_plugin import BasePlugin
from plugins.calendar.constants import LOCALE_MAP, FONT_SIZES
from PIL import Image, ImageColor, ImageDraw, ImageFont
import icalendar
import recurring_ical_events
from io import BytesIO
import logging
import requests
import hashlib
import time
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)

FETCH_ATTEMPTS = 3
FETCH_TIMEOUT = (10, 20)  # (connect, read) seconds
FETCH_DEADLINE_SECONDS = 45  # total budget per calendar, retries included
RETRY_BACKOFF_SECONDS = 3

class Calendar(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        template_params['locale_map'] = LOCALE_MAP
        return template_params

    def generate_image(self, settings, device_config):
        calendar_urls = settings.get('calendarURLs[]')
        calendar_colors = settings.get('calendarColors[]')
        view = settings.get("viewMode")

        if not view:
            raise RuntimeError("View is required")
        elif view not in ["timeGridDay", "timeGridWeek", "dayGrid", "dayGridMonth", "listMonth"]:
            raise RuntimeError("Invalid view")

        if not calendar_urls:
            raise RuntimeError("At least one calendar URL is required")
        for url in calendar_urls:
            if not url.strip():
                raise RuntimeError("Invalid calendar URL")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        
        timezone = device_config.get_config("timezone", default="America/New_York")
        time_format = device_config.get_config("time_format", default="12h")
        tz = pytz.timezone(timezone)

        current_dt = datetime.now(tz)
        start, end = self.get_view_range(view, current_dt, settings)
        # Aware bounds: naive ones are interpreted as UTC by recurring_ical_events,
        # which dropped events between local midnight and the UTC offset.
        start, end = self._localize(start, tz), self._localize(end, tz)
        logger.debug(f"Fetching events for {start} --> [{current_dt}] --> {end}")
        events = self.fetch_ics_events(calendar_urls, calendar_colors, tz, start, end)
        if not events:
            logger.warning("No events found for ics url")

        if view == 'timeGridWeek' and settings.get("displayPreviousDays") != "true":
            view = 'timeGrid'

        template_params = {
            "view": view,
            "events": events,
            "current_dt": current_dt.replace(minute=0, second=0, microsecond=0).isoformat(),
            "timezone": timezone,
            "plugin_settings": settings,
            "time_format": time_format,
            "font_scale": FONT_SIZES.get(settings.get("fontSize", "normal"))
        }

        image = self.render_image(dimensions, "calendar.html", "calendar.css", template_params)

        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")
        return image
    
    def fetch_ics_events(self, calendar_urls, colors, tz, start_range, end_range):
        parsed_events = []

        failures = []
        for calendar_url, color in zip(calendar_urls, colors):
            try:
                cal = self.fetch_calendar(calendar_url)
            except RuntimeError as e:
                # One unreachable calendar must not blank the whole display.
                logger.error(f"Skipping calendar {self._redact(calendar_url)}: {e}")
                failures.append(e)
                continue
            events = recurring_ical_events.of(cal).between(start_range, end_range)
            contrast_color = self.get_contrast_color(color)

            for event in events:
                start, end, all_day = self.parse_data_points(event, tz)
                parsed_event = {
                    "title": str(event.get("summary")),
                    "start": start,
                    "backgroundColor": color,
                    "textColor": contrast_color,
                    "allDay": all_day
                }
                if end:
                    parsed_event['end'] = end

                parsed_events.append(parsed_event)

        if failures and len(failures) == len(calendar_urls):
            raise RuntimeError(f"Failed to fetch all calendars: {failures[0]}")
        return parsed_events
    
    @staticmethod
    def _localize(dt, tz):
        """Attach tz to a naive datetime (floating ICS time / local bounds), convert aware ones."""
        if not isinstance(dt, datetime):
            return dt
        if dt.tzinfo is None:
            return tz.localize(dt)
        return dt.astimezone(tz)

    def get_view_range(self, view, current_dt, settings):
        start = datetime(current_dt.year, current_dt.month, current_dt.day)
        if view == "timeGridDay":
            end = start + timedelta(days=1)
        elif view == "timeGridWeek":
            if settings.get("displayPreviousDays") == "true":
                week_start_day = int(settings.get("weekStartDay", 1))
                python_week_start = (week_start_day - 1) % 7
                offset = (current_dt.weekday() - python_week_start) % 7
                start = current_dt - timedelta(days=offset)
                start = datetime(start.year, start.month, start.day)
            end = start + timedelta(days=7)
        elif view == "dayGrid":
            start = current_dt - timedelta(weeks=1)
            end = current_dt + timedelta(weeks=int(settings.get("displayWeeks") or 4))
        elif view == "dayGridMonth":
            start = datetime(current_dt.year, current_dt.month, 1) - timedelta(weeks=1)
            end = datetime(current_dt.year, current_dt.month, 1) + timedelta(weeks=6)
        elif view == "listMonth":
            end = start + timedelta(weeks=5)
        return start, end
        
    def parse_data_points(self, event, tz):
        all_day = False
        dtstart = event.decoded("dtstart")
        if isinstance(dtstart, datetime):
            dtstart = self._localize(dtstart, tz)
            start = dtstart.isoformat()
        else:
            start = dtstart.isoformat()
            all_day = True

        end = None
        if "dtend" in event:
            dtend = event.decoded("dtend")
            if isinstance(dtend, datetime):
                end = self._localize(dtend, tz).isoformat()
            else:
                end = dtend.isoformat()
        elif "duration" in event:
            duration = event.decoded("duration")
            dtend = dtstart + duration
            end = self._localize(dtend, tz).isoformat() if isinstance(dtend, datetime) else dtend.isoformat()
        return start, end, all_day

    def fetch_calendar(self, calendar_url):
        """Fetch and parse an ICS feed, with retries and a last-known-good disk cache."""
        # workaround for webcal urls
        if calendar_url.startswith("webcal://"):
            calendar_url = calendar_url.replace("webcal://", "https://")

        cache_path = self._cache_path(calendar_url)
        last_error = None
        deadline = time.monotonic() + FETCH_DEADLINE_SECONDS
        for attempt in range(1, FETCH_ATTEMPTS + 1):
            try:
                response = requests.get(calendar_url, timeout=FETCH_TIMEOUT)
                response.raise_for_status()
                cal = icalendar.Calendar.from_ical(response.text)
                self._write_cache(cache_path, response.text)
                return cal
            except Exception as e:
                last_error = e
                logger.warning(f"Calendar fetch attempt {attempt}/{FETCH_ATTEMPTS} failed for "
                               f"{self._redact(calendar_url)}: {type(e).__name__}")
                backoff = RETRY_BACKOFF_SECONDS * attempt
                # Only retry if a full attempt still fits in the time budget
                if attempt == FETCH_ATTEMPTS or \
                        time.monotonic() + backoff + sum(FETCH_TIMEOUT) > deadline:
                    break
                time.sleep(backoff)

        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cal = icalendar.Calendar.from_ical(f.read())
                age_h = (time.time() - os.path.getmtime(cache_path)) / 3600
                logger.warning(f"Using cached calendar for {self._redact(calendar_url)} ({age_h:.1f}h old)")
                return cal
            except Exception as e:
                logger.error(f"Failed to read calendar cache {cache_path}: {e}")

        raise RuntimeError(f"Failed to fetch iCalendar url {self._redact(calendar_url)}: {last_error}")

    def _cache_path(self, calendar_url):
        digest = hashlib.sha256(calendar_url.encode("utf-8")).hexdigest()[:32]
        return os.path.join(self.get_plugin_dir("cache"), f"{digest}.ics")

    @staticmethod
    def _write_cache(cache_path, text):
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            tmp_path = cache_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp_path, cache_path)
        except OSError as e:
            logger.warning(f"Could not write calendar cache: {e}")

    @staticmethod
    def _redact(url):
        """Strip query string/path secrets (private ICS tokens) from logs."""
        try:
            from urllib.parse import urlsplit
            parts = urlsplit(url)
            return f"{parts.scheme}://{parts.netloc}/..."
        except Exception:
            return "<calendar url>"

    def get_contrast_color(self, color):
        """
        Returns '#000000' (black) or '#ffffff' (white) depending on the contrast
        against the given color.
        """
        r, g, b = ImageColor.getrgb(color)
        # YIQ formula to estimate brightness
        yiq = (r * 299 + g * 587 + b * 114) / 1000

        return '#000000' if yiq >= 150 else '#ffffff'
