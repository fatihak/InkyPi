"""
APOD Plugin for InkyPi
This plugin fetches the Astronomy Picture of the Day (APOD) from the new NASA's API
and displays it on the InkyPi device. It supports optional manual date selection or random dates.
"""

from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
from io import BytesIO
from utils.http_client import get_http_session
import logging
from random import randint
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class Apod(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = False
        return template_params

    def generate_image(self, settings, device_config):
        logger.info("=== APOD Plugin: Starting image generation ===")

        # Determine date to fetch
        if settings.get("randomizeApod") == "true":
            start = datetime(2015, 1, 1)
            end = datetime.today()
            delta_days = (end - start).days
            random_date = start + timedelta(days=randint(0, delta_days))
            apod_date = random_date.strftime("%y%m%d")
            logger.info(f"Fetching random APOD from date: {apod_date}")
        elif settings.get("customDate"):
            apod_date = datetime.strptime(settings["customDate"], "%Y-%m-%d").strftime("%y%m%d")
            logger.info(f"Fetching APOD from custom date: {apod_date}")
        else:
            apod_date = datetime.today().strftime("%y%m%d")
            logger.info("Fetching today's APOD")

        logger.debug("Requesting NASA APOD API...")
        session = get_http_session()
        url = f"https://science.nasa.gov/wp-json/wp/v2/apod-basic/{apod_date}"
        response = session.get(url)

        if response.status_code != 200:
            logger.error(f"NASA API error (status {response.status_code}): {response.text}")
            raise RuntimeError("Failed to retrieve NASA APOD.")

        data = response.json()
        logger.debug(f"APOD API response received: {data.get('title', 'No title')}")

        if data.get("media_type") != "image":
            logger.warning(f"APOD media type is '{data.get('media_type')}', not 'image'")
            raise RuntimeError("APOD is not an image today.")

        image_url = data.get("hdurl") or data.get("url")
        logger.info(f"APOD image URL: {image_url}")
        logger.debug(f"Using {'HD URL' if data.get('hdurl') else 'standard URL'}")

        # Get target dimensions
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
            logger.debug(f"Vertical orientation detected, dimensions: {dimensions[0]}x{dimensions[1]}")

        # Use adaptive image loader for memory-efficient processing
        image = self.image_loader.from_url(image_url, dimensions, timeout_ms=40000)

        if not image:
            logger.error("Failed to load APOD image")
            raise RuntimeError("Failed to load APOD image.")

        logger.info("=== APOD Plugin: Image generation complete ===")
        return image
