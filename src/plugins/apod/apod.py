"""
APOD Plugin for InkyPi
This plugin fetches the Astronomy Picture of the Day (APOD) from NASA's API
and displays it on the InkyPi device. It supports optional manual date selection or random dates.
For the API key, set `NASA_SECRET={API_KEY}` in your .env file.
"""

from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
from io import BytesIO
import requests
import logging
from random import randint
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class Apod(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "NASA",
            "expected_key": "NASA_SECRET"
        }
        template_params['style_settings'] = False
        return template_params

    def generate_image(self, settings, device_config):
        logger.info(f"APOD plugin settings: {settings}")

        api_key = device_config.load_env_key("NASA_SECRET")
        if not api_key:
            raise RuntimeError("NASA API Key not configured.")

        params = {"api_key": api_key}

        if settings.get("randomizeApod") == "true":
            start = datetime(2015, 1, 1)
            end = datetime.today()
            delta_days = (end - start).days
            random_date = start + timedelta(days=randint(0, delta_days))
            params["date"] = random_date.strftime("%Y-%m-%d")
        elif settings.get("customDate"):
            params["date"] = settings["customDate"]

        response = requests.get("https://api.nasa.gov/planetary/apod", params=params)

        if response.status_code != 200:
            logger.error(f"NASA API error: {response.text}")
            raise RuntimeError("Failed to retrieve NASA APOD.")

        data = response.json()

        if data.get("media_type") != "image":
            raise RuntimeError("APOD is not an image today.")

        image_url = data.get("hdurl") or data.get("url")

        try:
            img_data = requests.get(image_url)
            image = Image.open(BytesIO(img_data.content))
        except Exception as e:
            logger.error(f"Failed to load APOD image: {str(e)}")
            raise RuntimeError("Failed to load APOD image.")

        return image