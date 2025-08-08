from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageOps, ImageColor
from io import BytesIO
import feedparser
import re

logger = logging.getLogger(__name__)

COMICS = [
    "XKCD",
    "Saturday Morning Breakfast Cereal",
    "The Oatmeal",
    "The Perry Bible Fellowship",
    "Questionable Content"
]

class Comic(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['comics'] = COMICS
        return template_params

    def generate_image(self, settings, device_config):
        comic = settings.get("comic")
        if not comic or comic not in COMICS:
            raise RuntimeError("Invalid comic provided.")

        image_url = self.get_image_url(comic)
        if not image_url:
            raise RuntimeError("Failed to retrieve latest comic url.")
        
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        width, height = dimensions
        
        response = requests.get(image_url, stream=True)
        response.raise_for_status()

        with Image.open(response.raw) as img:
            img.thumbnail((width, height), Image.LANCZOS)
            background = Image.new("RGB", (width, height), "white")
            background.paste(img, ((width - img.width) // 2, (height - img.height) // 2))
            return background

    def get_image_url(self, comic):
        if comic == "XKCD":
            feed = feedparser.parse("https://xkcd.com/atom.xml")
            summary = feed.entries[0].summary
            src = re.search(r'<img[^>]+src="([^"]+)"', summary).group(1)
        elif comic == "Saturday Morning Breakfast Cereal":
            feed = feedparser.parse("http://www.smbc-comics.com/comic/rss")
            desc = feed.entries[0].description
            src = re.search(r'<img[^>]+src="([^"]+)"', desc).group(1)
        elif comic == "The Oatmeal":
            feed = feedparser.parse("http://theoatmeal.com/feed/rss")
            desc = feed.entries[0].description
            src = re.search(r'<img[^>]+src="([^"]+)"', desc).group(1)
        elif comic == "Questionable Content":
            feed = feedparser.parse("http://www.questionablecontent.net/QCRSS.xml")
            desc = feed.entries[0].description
            src = re.search(r'<img[^>]+src="([^"]+)"', desc)
        elif comic == "The Perry Bible Fellowship":
            url = "https://pbfcomics.com/feed/"
            feed = feedparser.parse(url)
            desc = feed.entries[0].description
            src = re.search(r"<img[^>]+src=['\"]([^'\"]+)['\"]", desc).group(1)
        return src