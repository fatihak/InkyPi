"""
APOD Plugin for InkyPi
This plugin fetches the Astronomy Picture of the Day (APOD) from NASA's API
and displays it on the InkyPi device. It supports optional manual date selection or random dates.
For the API key, set `NASA_SECRET={API_KEY}` in your .env file.
"""
import numpy as np

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

        if settings.get('autoResize') == 'true':
            inky_res = device_config.config.get('resolution')
            if settings.get('autoBgColor') == 'true':
                bg = Apod.average_border_color(image)
            else:
                bg = 0, 0, 0

            image = self.fit_with_background(
                image,
                inky_res,
                bg
            )
            pass
        return image

    @staticmethod
    def resize_to_fit(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
        target_w, target_h = target_size

        img = img.copy()
        img.thumbnail((target_w, target_h), Image.LANCZOS)

        return img

    @staticmethod
    def fit_with_background(
        img: Image.Image,
        target_size: tuple[int, int],
        background=(255, 255, 255)
    ) -> Image.Image:
        img = Apod.resize_to_fit(img, target_size)

        canvas = Image.new("RGB", target_size, background)
        x = (target_size[0] - img.width) // 2
        y = (target_size[1] - img.height) // 2

        canvas.paste(img, (x, y))
        return canvas

    @staticmethod
    def average_border_color(img: Image.Image, border_px: int = 10):
        img = img.convert("RGB")
        w, h = img.size

        pixels = []

        # Top & bottom
        for y in range(border_px):
            pixels.extend(img.crop((0, y, w, y + 1)).getdata())
            pixels.extend(img.crop((0, h - y - 1, w, h - y)).getdata())

        # Left & right
        for x in range(border_px):
            pixels.extend(img.crop((x, 0, x + 1, h)).getdata())
            pixels.extend(img.crop((w - x - 1, 0, w - x, h)).getdata())

        return tuple(map(int, np.mean(pixels, axis=0)))

