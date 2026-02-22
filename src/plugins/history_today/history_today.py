from plugins.base_plugin.base_plugin import BasePlugin
from utils.http_client import get_http_session
from datetime import date
import logging
import random

logger = logging.getLogger(__name__)

WIKIPEDIA_URL = "https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{month}/{day}"


class HistoryToday(BasePlugin):

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        count = int(settings.get("count", 5))
        today = date.today()

        events = self._fetch_events(today.month, today.day, count)

        template_params = {
            "events": events,
            "month_day": today.strftime("%B %d"),
            "plugin_settings": settings,
        }

        return self.render_image(dimensions, "history_today.html", "history_today.css", template_params)

    def _fetch_events(self, month, day, count):
        session = get_http_session()
        try:
            resp = session.get(
                WIKIPEDIA_URL.format(month=month, day=day),
                headers={"Accept": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            events = data.get("events", [])
            # Pick a random selection for variety
            if len(events) > count:
                events = random.sample(events, count)
            return [{"year": e.get("year", ""), "text": e.get("text", "")} for e in events]
        except Exception as e:
            logger.error("Wikipedia On This Day fetch failed: %s", e)
            return []
