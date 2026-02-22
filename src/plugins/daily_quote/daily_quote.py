from plugins.base_plugin.base_plugin import BasePlugin
from utils.http_client import get_http_session
import logging
import random

logger = logging.getLogger(__name__)

ZENQUOTES_URL = "https://zenquotes.io/api/random"

FALLBACK_QUOTES = [
    {"q": "The only way to do great work is to love what you do.", "a": "Steve Jobs"},
    {"q": "In the middle of difficulty lies opportunity.", "a": "Albert Einstein"},
    {"q": "Simplicity is the ultimate sophistication.", "a": "Leonardo da Vinci"},
    {"q": "The best time to plant a tree was 20 years ago. The second best time is now.", "a": "Chinese Proverb"},
    {"q": "Be yourself; everyone else is already taken.", "a": "Oscar Wilde"},
    {"q": "Do what you can, with what you have, where you are.", "a": "Theodore Roosevelt"},
    {"q": "It does not matter how slowly you go as long as you do not stop.", "a": "Confucius"},
    {"q": "Life is what happens when you're busy making other plans.", "a": "John Lennon"},
    {"q": "The unexamined life is not worth living.", "a": "Socrates"},
    {"q": "To be or not to be, that is the question.", "a": "William Shakespeare"},
    {"q": "I think, therefore I am.", "a": "Rene Descartes"},
    {"q": "That which does not kill us makes us stronger.", "a": "Friedrich Nietzsche"},
    {"q": "Not all those who wander are lost.", "a": "J.R.R. Tolkien"},
    {"q": "The journey of a thousand miles begins with a single step.", "a": "Lao Tzu"},
    {"q": "Stay hungry, stay foolish.", "a": "Steve Jobs"},
]


class DailyQuote(BasePlugin):

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        font_size = settings.get("font_size", "normal")

        quote_data = self._fetch_quote()

        template_params = {
            "quote": quote_data["q"],
            "author": quote_data["a"],
            "font_size": font_size,
            "plugin_settings": settings,
        }

        image = self.render_image(
            dimensions, "daily_quote.html", "daily_quote.css", template_params
        )
        return image

    def _fetch_quote(self):
        session = get_http_session()
        try:
            resp = session.get(ZENQUOTES_URL, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data and isinstance(data, list) and "q" in data[0]:
                return data[0]
        except Exception as e:
            logger.error("ZenQuotes fetch failed: %s", e)

        return random.choice(FALLBACK_QUOTES)
