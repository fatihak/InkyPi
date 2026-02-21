from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageOps, ImageColor
import logging
import os
import random

from utils.image_utils import pad_image_blur

logger = logging.getLogger(__name__)

def list_files_in_folder(folder_path):
    """Return a list of image file paths in the given folder, excluding hidden files."""
    image_extensions = ('.avif', '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heif', '.heic')
    image_files = []
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            if f.lower().endswith(image_extensions) and not f.startswith('.'):
                image_files.append(os.path.join(root, f))

    return image_files

class ImageFolder(BasePlugin):
    def generate_image(self, settings, device_config):
        logger.info("=== Image Folder Plugin: Starting image generation ===")

        folder_path = settings.get('folder_path')
        if not folder_path:
            logger.error("No folder path provided in settings")
            raise RuntimeError("Folder path is required.")

        if not os.path.exists(folder_path):
            logger.error(f"Folder does not exist: {folder_path}")
            raise RuntimeError(f"Folder does not exist: {folder_path}")

        if not os.path.isdir(folder_path):
            logger.error(f"Path is not a directory: {folder_path}")
            raise RuntimeError(f"Path is not a directory: {folder_path}")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
            logger.debug(f"Vertical orientation detected, dimensions: {dimensions[0]}x{dimensions[1]}")

        logger.info(f"Scanning folder: {folder_path}")
        image_files = list_files_in_folder(folder_path)

        if not image_files:
            logger.warning(f"No image files found in folder: {folder_path}")
            raise RuntimeError(f"No image files found in folder: {folder_path}")

        logger.debug(f"Found {len(image_files)} image file(s) in folder")
        image_url = random.choice(image_files)
        logger.info(f"Selected random image: {os.path.basename(image_url)}")
        logger.debug(f"Full path: {image_url}")

        # Check padding options
        use_padding = settings.get('padImage') == "true"
        background_option = settings.get('backgroundOption', 'blur')
        logger.debug(f"Settings: pad_image={use_padding}, background_option={background_option}")

        try:
            # Use adaptive loader for memory-efficient processing
            # Load without auto-resize first to handle padding options
            # Note: Loader automatically handles EXIF orientation correction
            img = self.image_loader.from_file(image_url, dimensions, resize=False)

            if not img:
                raise RuntimeError("Failed to load image from file")

            if use_padding:
                logger.debug(f"Applying padding with {background_option} background")
                if background_option == "blur":
                    img = pad_image_blur(img, dimensions)
                else:
                    background_color = ImageColor.getcolor(settings.get('backgroundColor') or "white", img.mode)
                    img = ImageOps.pad(img, dimensions, color=background_color, method=Image.Resampling.LANCZOS)
            else:
                # No padding requested, scale to fit dimensions (crop to preserve aspect ratio)
                logger.debug(f"Scaling to fit dimensions: {dimensions[0]}x{dimensions[1]}")
                img = ImageOps.fit(img, dimensions, method=Image.LANCZOS)

            return img
        except Exception as e:
            logger.error(f"Error loading image from {image_url}: {e}")
            raise RuntimeError("Failed to load image, please check logs.")

        logger.info("=== Image Folder Plugin: Image generation complete ===")
        return img
