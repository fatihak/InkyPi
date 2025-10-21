from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageOps, ImageColor
import logging
import random

from utils.image_utils import pad_image_blur

logger = logging.getLogger(__name__)


class ImageUpload(BasePlugin):
    def open_image(self, img_index: int, image_locations: list) -> Image:
        if not image_locations:
            raise RuntimeError("No images provided.")
        # Open the image using Pillow
        try:
            image = Image.open(image_locations[img_index])
        except Exception as e:
            logger.error(f"Failed to read image file: {str(e)}")
            raise RuntimeError("Failed to read image file.")
        return image
        

    def generate_image(self, settings, device_config) -> Image:
        # Get the current index from the device json
        img_index = settings.get("image_index", 0)
        image_locations = settings.get("imageFiles[]")

        if img_index >= len(image_locations):
            # Prevent Index out of range issues when file list has changed
            img_index = 0

        if settings.get('randomize') == "true":
            img_index = random.randrange(0, len(image_locations))
            image = self.open_image(img_index, image_locations)
        else:
            image = self.open_image(img_index, image_locations)
            img_index = (img_index + 1) % len(image_locations)

        # Write the new index back ot the device json
        settings['image_index'] = img_index
        orientation = device_config.get_config("orientation")

        if settings.get('padImage') == "true":
            dimensions = device_config.get_resolution()
            if orientation == "vertical":
                dimensions = dimensions[::-1]

            if settings.get('backgroundOption') == "blur":
                return pad_image_blur(image, dimensions)
            else:
                background_color = ImageColor.getcolor(settings.get('backgroundColor') or (255, 255, 255), "RGB")
                return ImageOps.pad(image, dimensions, color=background_color, method=Image.Resampling.LANCZOS)
        return image
