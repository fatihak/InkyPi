from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
from utils.image_utils import take_screenshot_html

logger = logging.getLogger(__name__)

class Screenshot(BasePlugin):
    def generate_image(self, settings, device_config):

        url = settings.get('url')
        if not url:
            raise RuntimeError("URL is required.")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        image = take_screenshot(url, dimensions)

        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")

        return image