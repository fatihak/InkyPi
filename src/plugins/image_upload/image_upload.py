from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageOps, ImageColor
import logging
import random
import os

from utils.image_utils import pad_image_blur

logger = logging.getLogger(__name__)


class ImageUpload(BasePlugin):
    def open_image(self, img_index: int, image_locations: list, dimensions: tuple, resize: bool = True) -> Image:
        """
        Open image with adaptive loader for memory efficiency.

        Args:
            img_index: Index of image to load
            image_locations: List of image paths
            dimensions: Target dimensions
            resize: Whether to auto-resize (set False if manual padding needed)
        """
        if not image_locations:
            raise RuntimeError("No images provided.")

        try:
            # Use adaptive loader for memory-efficient processing
            image = self.image_loader.from_file(image_locations[img_index], dimensions, resize=resize)
            if not image:
                raise RuntimeError("Failed to load image from file")
            return image
        except Exception as e:
            logger.error(f"Failed to read image file: {str(e)}")
            raise RuntimeError("Failed to read image file.")


    def generate_image(self, settings, device_config) -> Image:
        logger.info("=== Image Upload Plugin: Starting image generation ===")

        # Get the current index from the device json
        img_index = settings.get("image_index", 0)
        image_locations = settings.get("imageFiles[]")

        if not image_locations:
            logger.error("No images uploaded")
            raise RuntimeError("No images provided.")

        logger.debug(f"Total uploaded images: {len(image_locations)}")
        logger.debug(f"Current index: {img_index}")

        if img_index >= len(image_locations):
            # Prevent Index out of range issues when file list has changed
            logger.warning(f"Index {img_index} out of range, resetting to 0")
            img_index = 0

        # Get dimensions
        dimensions = device_config.get_resolution()
        orientation = device_config.get_config("orientation")
        if orientation == "vertical":
            dimensions = dimensions[::-1]
            logger.debug(f"Vertical orientation detected, dimensions: {dimensions[0]}x{dimensions[1]}")

        # Determine if we need manual padding
        needs_padding = settings.get('padImage') == "true"
        is_random = settings.get('randomize') == "true"
        background_option = settings.get('backgroundOption', 'blur')

        logger.debug(f"Settings: randomize={is_random}, pad_image={needs_padding}, background_option={background_option}")

        # Load image (without auto-resize if padding needed)
        if is_random:
            img_index = random.randrange(0, len(image_locations))
            logger.info(f"Random mode: Selected image index {img_index}")
            image = self.open_image(img_index, image_locations, dimensions, resize=not needs_padding)
        else:
            logger.info(f"Sequential mode: Loading image index {img_index}")
            image = self.open_image(img_index, image_locations, dimensions, resize=not needs_padding)
            img_index = (img_index + 1) % len(image_locations)
            logger.debug(f"Next index will be: {img_index}")

        # Write the new index back to the device json
        settings['image_index'] = img_index

        # Apply padding if requested
        if needs_padding:
            logger.debug(f"Applying padding with {background_option} background")
            if background_option == "blur":
                image = pad_image_blur(image, dimensions)
            else:
                background_color = ImageColor.getcolor(settings.get('backgroundColor') or "white", image.mode)
                image = ImageOps.pad(image, dimensions, color=background_color, method=Image.Resampling.LANCZOS)

        logger.info("=== Image Upload Plugin: Image generation complete ===")
        return image

    def cleanup(self, settings):
        """Delete all uploaded image files associated with this plugin instance."""
        image_locations = settings.get("imageFiles[]", [])
        if not image_locations:
            return

        for image_path in image_locations:
            if os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    logger.info(f"Deleted uploaded image: {image_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete uploaded image {image_path}: {e}")
