from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
from io import BytesIO
import feedparser
import requests
import logging

logger = logging.getLogger(__name__)

FONT_SIZES = {
    "x-small": 0.7,
    "small": 0.9,
    "normal": 1,
    "large": 1.1,
    "x-large": 1.3
}

class Rss(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        
        title = settings.get("title")
        feed_url = settings.get("feedUrl")
        if not feed_url:
            raise RuntimeError("RSS Feed Url is required.")
        
        items = self.parse_rss_feed(feed_url)

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        template_params = {
            "title": title,
            "include_images": settings.get("includeImages", False),
            "items": items[:10],
            "font_scale": FONT_SIZES.get(settings.get('fontSize', 'normal'), 1),
            "plugin_settings": settings
        }

        image = self.render_image(dimensions, "rss.html", "rss.css", template_params)
        return image
    
    def parse_rss_feed(self, url, timeout=10):
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        
        # Parse the feed content
        feed = feedparser.parse(resp.content)
        items = []

        for entry in feed.entries:
            item = {
                "title": entry.get("title", ""),
                "description": entry.get("description", ""),
                "published": entry.get("published", ""),
                "link": entry.get("link", ""),
                "image": None
            }

            # Try to extract image from common RSS fields
            if "media_content" in entry and len(entry.media_content) > 0:
                item["image"] = entry.media_content[0].get("url")
            elif "media_thumbnail" in entry and len(entry.media_thumbnail) > 0:
                item["image"] = entry.media_thumbnail[0].get("url")
            elif "enclosures" in entry and len(entry.enclosures) > 0:
                item["image"] = entry.enclosures[0].get("url")

            items.append(item)

        return items