from plugins.base_plugin.base_plugin import BasePlugin
from datetime import datetime, timedelta
from utils.image_utils import get_image
from PIL import Image
import logging
from plugins.newspaper.constants import NEWSPAPERS

logger = logging.getLogger(__name__)

FREEDOM_FORUM_URL = "https://cdn.freedomforum.org/dfp/jpg{}/lg/{}.jpg"
class Newspaper(BasePlugin):
    def generate_image(self, settings, device_config):
        newspaper_slug = settings.get('newspaperSlug')

        if not newspaper_slug:
            raise RuntimeError("Newspaper input not provided.")
        newspaper_slug = newspaper_slug.upper()

        # Get today's date
        today = datetime.today()

        # check the next day, then today, then prior day
        days = [today + timedelta(days=diff) for diff in [1,0,-1,-2]]

        image = None
        for date in days:
            image_url = FREEDOM_FORUM_URL.format(date.day, newspaper_slug)
            image = get_image(image_url)
            if image:
                logging.info(f"Found {newspaper_slug} front cover for {date.strftime('%Y-%m-%d')}")
                break

        if image:
            # expand height if newspaper is wider than resolution
            img_width, img_height = image.size

            dimensions = device_config.get_resolution()
            if device_config.get_config("orientation") == "horizontal":
                dimensions = dimensions[::-1]

            desired_width, desired_height = dimensions

            img_ratio = img_width / img_height
            desired_ratio = desired_width / desired_height

            if img_ratio < desired_ratio:
                new_height =  int((img_width*desired_width) / desired_height)
                new_image = Image.new("RGB", (img_width, new_height), (255, 255, 255))
                new_image.paste(image, (0, 0))
                image = new_image
        else:
            raise RuntimeError("Newspaper front cover not found.")
    
        return image
    
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['newspapers'] = sorted(NEWSPAPERS, key=lambda n: n['name'])
        return template_params