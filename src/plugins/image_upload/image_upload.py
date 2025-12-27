from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageOps, ImageColor
from io import BytesIO
import logging
import random
import json
import re

logger = logging.getLogger(__name__)


class ImageUpload(BasePlugin):

    def __safeId(self, value):
        return '' if value == None else re.sub(r'[^a-zA-Z0-9_\-]', '_', re.sub(r'^.*[\\/]', '', value))

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
            current_index = img_index
            image = self.open_image(img_index, image_locations)
        else:
            image = self.open_image(img_index, image_locations)
            current_index = img_index
            img_index = (img_index + 1) % len(image_locations)

        file_id = self.__safeId(image_locations[current_index])

        # Write the new index back ot the device json
        settings['image_index'] = img_index

        background_color = ImageColor.getcolor(settings.get('backgroundColor') or (255, 255, 255), "RGB")

        crop_settings = settings.get(f'crop_settings[{file_id}]')
        crop_params = json.loads(crop_settings or '{}')
        if len(crop_params) > 0:
            rotate = crop_params['rotate']
            if rotate != 0:
                image = image.rotate(-rotate, expand=True)

            temp = Image.new('RGB', (crop_params['width'], crop_params['height']), background_color)
            temp.paste(image, (-crop_params['x'], -crop_params['y']))
            image = temp

        ###
        if settings.get('padImage') == "true":
            dimensions = device_config.get_resolution()
            if device_config.get_config("orientation") == "vertical":
                dimensions = dimensions[::-1]
            frame_ratio = dimensions[0] / dimensions[1]
            img_width, img_height = image.size
            padded_img_size = (int(img_height * frame_ratio) if img_width >= img_height else img_width,
                              img_height if img_width >= img_height else int(img_width / frame_ratio))
            return ImageOps.pad(image, padded_img_size, color=background_color, method=Image.Resampling.LANCZOS)
        return image
