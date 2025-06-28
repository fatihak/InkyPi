from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageOps, ImageColor
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
        ###
        if settings.get('padImage') == "true":
            dimensions = device_config.get_resolution()
            if device_config.get_config("orientation") == "vertical":
                dimensions = dimensions[::-1]
            frame_ratio = dimensions[0] / dimensions[1]
            img_width, img_height = image.size
            padded_img_size = (int(img_height * frame_ratio) if img_width >= img_height else img_width,
                              img_height if img_width >= img_height else int(img_width / frame_ratio))
            background_color = ImageColor.getcolor(settings.get('backgroundColor') or (255, 255, 255), "RGB")
            return ImageOps.pad(image, padded_img_size, color=background_color, method=Image.Resampling.LANCZOS)
        return image