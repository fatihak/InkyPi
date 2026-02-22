from plugins.base_plugin.base_plugin import BasePlugin
from utils.http_client import get_http_session
import logging

logger = logging.getLogger(__name__)

JOKEAPI_URL = "https://v2.jokeapi.dev/joke/{category}"

CATEGORIES = ["Any", "Programming", "Misc", "Pun", "Spooky", "Christmas"]

FALLBACK_JOKES = [
    {"type": "twopart", "setup": "Why do programmers prefer dark mode?", "delivery": "Because light attracts bugs!", "category": "Programming"},
    {"type": "twopart", "setup": "Why did the programmer quit his job?", "delivery": "Because he didn't get arrays!", "category": "Programming"},
    {"type": "single", "joke": "A SQL query walks into a bar, walks up to two tables and asks... 'Can I join you?'", "category": "Programming"},
    {"type": "twopart", "setup": "How many programmers does it take to change a light bulb?", "delivery": "None, that's a hardware problem.", "category": "Programming"},
]


class JokeOfDay(BasePlugin):

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        template_params['categories'] = CATEGORIES
        return template_params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        category = settings.get("category", "Any")
        safe_mode = settings.get("safe_mode", "true") == "true"

        joke_data = self._fetch_joke(category, safe_mode)

        template_params = {
            "joke_type": joke_data.get("type", "single"),
            "joke": joke_data.get("joke", ""),
            "setup": joke_data.get("setup", ""),
            "delivery": joke_data.get("delivery", ""),
            "category": joke_data.get("category", category),
            "plugin_settings": settings,
        }

        return self.render_image(dimensions, "joke_of_day.html", "joke_of_day.css", template_params)

    def _fetch_joke(self, category, safe_mode):
        session = get_http_session()
        url = JOKEAPI_URL.format(category=category)
        url += "?safe-mode" if safe_mode else ""
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("error"):
                return data
        except Exception as e:
            logger.error("JokeAPI fetch failed: %s", e)
        import random
        return random.choice(FALLBACK_JOKES)
