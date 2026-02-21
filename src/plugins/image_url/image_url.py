from plugins.base_plugin.base_plugin import BasePlugin
import logging

logger = logging.getLogger(__name__)

class ImageURL(BasePlugin):
    def generate_image(self, settings, device_config):
        logger.info("=== Image URL Plugin: Starting image generation ===")

        url = settings.get('url')
        if not url:
            logger.error("No URL provided in settings")
            raise RuntimeError("URL is required.")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
            logger.debug(f"Vertical orientation detected, dimensions: {dimensions[0]}x{dimensions[1]}")

        logger.info(f"Fetching image from URL: {url}")
        logger.debug(f"Target dimensions: {dimensions[0]}x{dimensions[1]}")

        # Use adaptive image loader for memory-efficient processing
        image = self.image_loader.from_url(url, dimensions, timeout_ms=40000)

        if not image:
            logger.error("Failed to load image from URL")
            raise RuntimeError("Failed to load image, please check logs.")

        logger.info("=== Image URL Plugin: Image generation complete ===")
        return image
