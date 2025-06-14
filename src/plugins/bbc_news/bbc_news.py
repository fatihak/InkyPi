import logging
import feedparser
import datetime
import requests
import base64
from plugins.base_plugin.base_plugin import BasePlugin
from io import BytesIO
from PIL import Image
import re

logger = logging.getLogger(__name__)

BBC_FEEDS = {
    "Top Stories": "http://feeds.bbci.co.uk/news/rss.xml",
    "World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "UK": "http://feeds.bbci.co.uk/news/uk/rss.xml",
    "Business": "http://feeds.bbci.co.uk/news/business/rss.xml",
    "Politics": "http://feeds.bbci.co.uk/news/politics/rss.xml",
    "Health": "http://feeds.bbci.co.uk/news/health/rss.xml",
    "Education & Family": "http://feeds.bbci.co.uk/news/education/rss.xml",
    "Science & Environment": "http://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "Technology": "http://feeds.bbci.co.uk/news/technology/rss.xml",
    "Entertainment & Arts": "http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    "UK - England": "http://feeds.bbci.co.uk/news/england/rss.xml",
    "UK - Northern Ireland": "http://feeds.bbci.co.uk/news/northern_ireland/rss.xml",
    "UK - Scotland": "http://feeds.bbci.co.uk/news/scotland/rss.xml",
    "UK - Wales": "http://feeds.bbci.co.uk/news/wales/rss.xml",
    "Sport": "http://feeds.bbci.co.uk/sport/rss.xml"
}

def clean_html(raw_html):
    """A simple function to strip HTML tags from a string."""
    if not raw_html:
        return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext

class BbcNews(BasePlugin):
    """
    BBC News Headlines Plugin for InkyPi.
    """

    def _get_thumbnail_url(self, entry):
        """Finds the thumbnail URL from an entry."""
        if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
            return entry.media_thumbnail[0].get('url')
        return ""

    def generate_settings_template(self):
        """Generates the template parameters for the settings page."""
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        template_params['bbc_feeds'] = BBC_FEEDS
        template_params["settings_template"] = "bbc_news/settings.html"
        return template_params

    def generate_image(self, settings, device_config):
        """Generates the BBC News headline image."""
        # --- 1. Determine Feed URL and Name ---
        feed_url = settings.get("bbc_feed_url", list(BBC_FEEDS.values())[0])
        feed_name = "BBC News"  # Default name
        for name, url in BBC_FEEDS.items():
            if url == feed_url:
                feed_name = name
                break

        # --- 2. Fetch and Parse Data ---
        logger.info(f"Fetching RSS feed from: {feed_url}")
        try:
            feed = feedparser.parse(feed_url)
            if feed.bozo or not hasattr(feed, 'version'):
                 raise ValueError("The provided URL does not point to a valid RSS feed.")
        except Exception as e:
            logger.error(f"Failed to fetch or parse RSS feed: {e}")
            raise RuntimeError(str(e))

        # --- 3. Process Feed Entries ---
        if not feed.entries:
            raise RuntimeError("The selected RSS feed is empty or has an unexpected format.")

        template_data = {
            "primary_story": None,
            "secondary_articles": [],
            "tertiary_articles": []
        }

        # Primary Story (First article)
        primary_entry = feed.entries[0]
        primary_thumb_url = self._get_thumbnail_url(primary_entry)
        summary = clean_html(primary_entry.summary)
        template_data["primary_story"] = {
            "title": primary_entry.title,
            "summary": summary,
            "thumbnail": primary_thumb_url
        }

        # Secondary Stories (Next 4 articles)
        secondary_entries = feed.entries[1:5]
        for entry in secondary_entries:
            thumb_url = self._get_thumbnail_url(entry)
            template_data["secondary_articles"].append({
                "title": entry.title,
                "thumbnail": thumb_url
            })

        # Tertiary Stories (Next 9 articles)
        tertiary_entries = feed.entries[5:14]
        for entry in tertiary_entries:
            template_data["tertiary_articles"].append({"title": entry.title})

        # --- 4. Prepare Template Parameters ---
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        template_params = {
            "data": template_data,
            "feed_name": feed_name,
            "current_time": datetime.datetime.now().strftime("%H:%M"),
            "current_date": datetime.datetime.now().strftime("%d %B %Y"),
            "plugin_settings": settings
        }

        # --- 5. Render the Image ---
        logger.info(f"Rendering BBC News HTML template at device resolution: {dimensions[0]}x{dimensions[1]}.")
        image = self.render_image(
            dimensions,
            "bbc_news.html",
            "bbc_news.css",
            template_params
        )
        return image
