from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageOps, ImageColor
import logging
import os
import random

from utils.image_utils import pad_image_blur

logger = logging.getLogger(__name__)

def list_files_in_folder(folder_path):
    """Return a list of image file paths in the given folder, excluding hidden files."""
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')
    image_files = []
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            if f.lower().endswith(image_extensions) and not f.startswith('.'):
                image_files.append(os.path.join(root, f))

    return image_files

class ImageFolder(BasePlugin):
    def generate_image(self, settings, device_config):
        folder_path = settings.get('folder_path')
        if not folder_path:
            raise RuntimeError("Folder path is required.")
        
        if not os.path.exists(folder_path):
            raise RuntimeError(f"Folder does not exist: {folder_path}")
        
        if not os.path.isdir(folder_path):
            raise RuntimeError(f"Path is not a directory: {folder_path}")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        logger.info(f"Grabbing a random image from: {folder_path}")

        image_files = list_files_in_folder(folder_path)
        if not image_files:
            raise RuntimeError(f"No image files found in folder: {folder_path}")

        image_url = random.choice(image_files)
        logger.info(f"Random image selected {image_url}")

        img = None
        try:
            img = Image.open(image_url)
            img = ImageOps.exif_transpose(img)  # Correct orientation using EXIF

            if settings.get('padImage') == "true":
                if settings.get('backgroundOption', 'blur') == "blur":
                    img = pad_image_blur(img, dimensions)
                else:
                    background_color = ImageColor.getcolor(settings.get('backgroundColor') or (255, 255, 255), "RGB")
                    img = ImageOps.pad(img, dimensions, color=background_color, method=Image.Resampling.LANCZOS)

        except Exception as e:
            logger.error(f"Error loading image from {image_url}: {e}")

        if not img:
            raise RuntimeError("Failed to load image, please check logs.")

        return img