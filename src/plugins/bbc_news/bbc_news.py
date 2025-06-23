import logging
import feedparser
import datetime
import re
import os
import base64
from plugins.base_plugin.base_plugin import BasePlugin
from io import BytesIO
from PIL import Image
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from utils.image_utils import take_screenshot_html

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
        """Intelligently finds the best thumbnail URL from an entry."""
        if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
            return entry.media_thumbnail[0].get('url')
        if hasattr(entry, 'media_content') and entry.media_content:
            for item in entry.media_content:
                if item.get('url') and item.get('medium') == 'image':
                    return item.get('url')
        if hasattr(entry, 'links'):
             for link in entry.links:
                if link.get('href', '').lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                    return link.href
        return ""

    def _get_article_counts(self, width, height, is_portrait):
        """
        Determines the optimal number of secondary and tertiary articles
        based on screen resolution and orientation.
        'width' and 'height' are logical dimensions for the current orientation.
        Returns: A tuple (num_secondary, num_tertiary).
        """
        # Note: 'width' parameter is the logical width for the current orientation.

        # Smallest screens:
        # - Landscape: up to 400px width (e.g., 400x300)
        # - Portrait: up to 300px width (e.g., 300x400)
        if not is_portrait and width <= 400: # Covers landscape up to 400px width
            return (4, 0)
        if is_portrait and width <= 300:     # Covers portrait up to 300px width
            return (4, 0)

        # Mid-size screens:
        # Order of landscape checks is important due to sequential evaluation.
        # - Landscape: 401px to 600px width
        if not is_portrait and width <= 600: # Catches 401-600px landscape
            return (4, 6) # Optimized for ~600px width landscape (e.g. 600x448)
        # - Landscape: 601px to 640px width
        if not is_portrait and width <= 640: # Catches 601-640px landscape
            return (4, 4) # Optimized for ~640px width landscape (e.g. 640x400)
        # - Portrait: 301px to 448px width
        if is_portrait and width <= 448:     # Catches 301-448px portrait
            return (3, 4)

        # Standard screens:
        # - Landscape: 641px to 800px width
        if not is_portrait and width <= 800: # Catches 641-800px landscape
            return (4, 9)
        # - Portrait: 449px to 480px width
        if is_portrait and width <= 480:     # Catches 449-480px portrait
            return (4, 6)

        # Large screens:
        # - Landscape: over 800px width
        if not is_portrait and width > 800:  # Catches >800px landscape
            return (8, 12)
        # - Portrait: over 480px width
        if is_portrait and width > 480:      # Catches >480px portrait
            return (8, 10)

        # Fallback for any resolutions not explicitly handled above.
        logger.warning(
            f"Article count fallback for: w={width}, h={height}, portrait={is_portrait}. Using default."
        )
        return (4, 6)

    def generate_settings_template(self):
        """Generates the template parameters for the settings page."""
        template_params = super().generate_settings_template()
        template_params['style_settings'] = False  # No style settings for this plugin yet
        template_params['bbc_feeds'] = BBC_FEEDS
        template_params["settings_template"] = "bbc_news/settings.html"
        return template_params

    def render_image(self, dimensions, html_file, css_file=None, template_params={}):
        """
        Overrides the BasePlugin's render_image method to create a self-contained
        HTML file with embedded CSS and fonts from the local plugin directory.
        """
        plugin_render_dir = self.get_plugin_dir("render")
        base_plugin_render_dir = os.path.join(Path(plugin_render_dir).parent.parent, "base_plugin", "render")

        loader = FileSystemLoader([plugin_render_dir, base_plugin_render_dir])
        env = Environment(loader=loader, autoescape=select_autoescape(['html', 'xml']))

        # Embed CSS
        css_content = ""
        with open(os.path.join(base_plugin_render_dir, "plugin.css"), 'r', encoding='utf-8') as f:
            css_content += f.read()
        with open(os.path.join(plugin_render_dir, css_file), 'r', encoding='utf-8') as f:
            css_content += f.read()
        template_params["embedded_css"] = css_content

        # Embed Fonts from local plugin 'fonts' directory
        font_faces = []
        plugin_fonts_dir = self.get_plugin_dir("fonts")
        if os.path.isdir(plugin_fonts_dir):
            for font_filename in os.listdir(plugin_fonts_dir):
                if font_filename.lower().endswith(('.ttf', '.otf')):
                    font_family_name = os.path.splitext(font_filename)[0].split('-')[0]
                    font_path = os.path.join(plugin_fonts_dir, font_filename)
                    with open(font_path, 'rb') as font_file:
                        font_data = base64.b64encode(font_file.read()).decode('utf-8')

                    font_faces.append({
                        "font_family": font_family_name,
                        "base64_url": f"data:font/truetype;charset=utf-8;base64,{font_data}",
                        "font_weight": "700" if "bold" in font_filename.lower() else "normal",
                        "font_style": "italic" if "italic" in font_filename.lower() else "normal"
                    })
        template_params["font_faces"] = font_faces

        template_params["width"], template_params["height"] = dimensions

        template = env.get_template(html_file)
        rendered_html = template.render(**template_params)

        return take_screenshot_html(rendered_html, dimensions)

    def generate_image(self, settings, device_config):
        """Generates the BBC News headline image."""
        feed_url = settings.get("bbc_feed_url", list(BBC_FEEDS.values())[0])
        feed_name = next((name for name, url in BBC_FEEDS.items() if url == feed_url), "BBC News")

        try:
            feed = feedparser.parse(feed_url)
            if feed.bozo or not hasattr(feed, 'version'):
                 raise ValueError("The provided URL does not point to a valid RSS feed.")
        except Exception as e:
            raise RuntimeError(f"Failed to parse RSS feed: {e}")

        if not feed.entries:
            raise RuntimeError("The selected RSS feed is empty or has an unexpected format.")

        dimensions = device_config.get_resolution()
        is_portrait = device_config.get_config("orientation") == "vertical"

        # Determine the correct width and height for logic based on orientation
        if is_portrait:
            logic_width, logic_height = dimensions[1], dimensions[0]
        else:
            logic_width, logic_height = dimensions[0], dimensions[1]

        num_secondary, num_tertiary = self._get_article_counts(logic_width, logic_height, is_portrait)

        # The dimensions for rendering are the logical width and height
        render_dimensions = (logic_width, logic_height)
        template_data = {
            "primary_story": None,
            "secondary_articles": [],
            "tertiary_articles": [],
            "main_content_class": "no-tertiary" if num_tertiary == 0 else ""
        }

        primary_entry = feed.entries[0]
        summary = clean_html(primary_entry.summary)
        template_data["primary_story"] = { "title": primary_entry.title, "summary": summary, "thumbnail": self._get_thumbnail_url(primary_entry) }
        template_data["secondary_articles"] = [{ "title": entry.title, "thumbnail": self._get_thumbnail_url(entry) } for entry in feed.entries[1:1+num_secondary]]
        template_data["tertiary_articles"] = [{ "title": entry.title } for entry in feed.entries[1+num_secondary : 1+num_secondary+num_tertiary]]

        template_params = {
            "data": template_data,
            "feed_name": feed_name,
            "current_time": datetime.datetime.now().strftime("%H:%M"),
            "current_date": datetime.datetime.now().strftime("%d %B %Y"),
            "plugin_settings": settings
        }

        image = self.render_image(
            render_dimensions,
            "bbc_news.html",
            "bbc_news.css",
            template_params
        )
        return image
