from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageOps, ImageColor
import logging
import random
import glob
import os

logger = logging.getLogger(__name__)


class ImageFolder(BasePlugin):

    def downsize_image(self, image: Image) -> Image:
        """
        Downsize an image using Pillow to 75% of its original size until its under 5k
        """

        scale_factor = 0.75

        # Downsample to under 5K if applicable
        while (True):
            width, height = image.size
            if width < 5000 and height < 5000:
                break

            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)

            # Use LANCZOS filter for high-quality downsampling
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
        return image

    def open_image(self, img_index: int, image_locations: list) -> Image:
        if not image_locations:
            raise RuntimeError("No images found in the folder provided.")

        # Open the image using Pillow
        try:
            image = Image.open(image_locations[img_index])
            image = self.downsize_image(image)
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

        # print(images_in_folder)

        img_index = random.randint(0, len(images_in_folder))
        image = self.open_image(img_index, images_in_folder)

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
