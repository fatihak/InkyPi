from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageOps, ImageColor
import logging
import random
import glob
import os

logger = logging.getLogger(__name__)


class ImageFolder(BasePlugin):

    def open_image(self, img_index: int, image_locations: list) -> Image:
        if not image_locations:
            raise RuntimeError("No images found in the folder provided.")
        
        # Check that the image is under 50 MB to prevent out of memory issues
        image_size_in_mb = os.path.getsize(image_locations[img_index]) / (1000 * 1000)
        if image_size_in_mb > 50:
            raise RuntimeError(f"image file {image_locations[img_index]} is required to be under 50 MB")
            

        # Open the image using Pillow
        try:
            image = Image.open(image_locations[img_index])
        except Exception as e:
            logger.error(f"Failed to read image file: {str(e)}")
            raise RuntimeError("Failed to read image file.")
        return image
        
    def generate_image(self, settings, device_config) -> Image:

        # Get the current index from the device json
        directory_to_search = settings.get('folderPath', '')

        # Get all files in the directory
        if not os.path.isdir(directory_to_search):
            raise RuntimeError(f"Provided folder path {directory_to_search} is not a folder")

        # Get a list of files in the folder
        images_in_folder = glob.glob(f"{directory_to_search}/**/*", recursive=True)

        img_index = random.randrange(0, len(images_in_folder))
        image = self.open_image(img_index, images_in_folder)

        # pad the image to the screen dimensions when enabled
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
