from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
from io import BytesIO
import logging

logger = logging.getLogger(__name__)

class ImageUpload(BasePlugin):
    def generate_image(self, settings, device_config):
        img_index = settings.get("image_index", 0)
        image_locations = settings.get("imageFiles[]")

        if img_index >= len(image_locations):
            # reset if image_locations changed
            img_index = 0

        if not image_locations:
            raise RuntimeError("No images provided.")
        # Open the image using Pillow
        try:
            image = Image.open(image_locations[img_index])
        except Exception as e:
            logger.error(f"Failed to read image file: {str(e)}")
            raise RuntimeError("Failed to read image file.")

        settings['image_index'] = (img_index + 1) % len(image_locations)
        return image