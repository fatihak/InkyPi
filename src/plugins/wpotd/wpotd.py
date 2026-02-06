"""
Wpotd Plugin for InkyPi
This plugin fetches the Wikipedia Picture of the Day (Wpotd) from Wikipedia's API
and displays it on the InkyPi device.

It supports optional manual date selection or random dates and can resize the image to fit the device's dimensions.

Wikipedia API Documentation: https://www.mediawiki.org/wiki/API:Main_page
Picture of the Day example: https://www.mediawiki.org/wiki/API:Picture_of_the_day_viewer
Github Repository: https://github.com/wikimedia/mediawiki-api-demos/tree/master/apps/picture-of-the-day-viewer
Wikimedia requires a User Agent header for API requests, which is set in the SESSION headers:
https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy

Flow:

1. Fetch the date to use for the Picture of the Day (POTD) based on settings. (_determine_date)
2. Make an API request to fetch the POTD data for that date. (_fetch_potd)
3. Extract the image filename from the response. (_fetch_potd)
4. Make another API request to get the image URL. (_fetch_image_src)
5. Download the image from the URL. (_download_image)
6. Optionally resize the image to fit the device dimensions. (_shrink_to_fit))
"""

from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, UnidentifiedImageError
from io import BytesIO
from utils.http_client import get_http_session
import logging
from random import randint
from datetime import datetime, timedelta, date
from functools import lru_cache
from typing import Dict, Any

logger = logging.getLogger(__name__)

class Wpotd(BasePlugin):
    HEADERS = {'User-Agent': 'InkyPi/1.0 (https://github.com/fatihak/InkyPi/)'}
    API_URL = "https://en.wikipedia.org/w/api.php"

    def generate_settings_template(self) -> Dict[str, Any]:
        template_params = super().generate_settings_template()
        template_params['style_settings'] = False
        return template_params

    def generate_image(self, settings: Dict[str, Any], device_config: Dict[str, Any]) -> Image.Image:
        logger.info("=== Wikipedia POTD Plugin: Starting image generation ===")

        datetofetch = self._determine_date(settings)
        logger.info(f"Fetching Wikipedia Picture of the Day for: {datetofetch}")
        logger.debug(f"Settings: shrink_to_fit={settings.get('shrinkToFitWpotd', 'false')}, randomize={settings.get('randomizeWpotd', 'false')}")

        data = self._fetch_potd(datetofetch)
        picurl = data["image_src"]
        logger.info(f"Image URL: {picurl}")
        logger.debug(f"Image filename: {data.get('filename', 'Unknown')}")

        # Get dimensions
        max_width, max_height = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            max_width, max_height = max_height, max_width
            logger.debug(f"Vertical orientation detected, dimensions: {max_width}x{max_height}")

        dimensions = (max_width, max_height)

        # Use adaptive loader if shrink-to-fit is enabled
        shrink_to_fit = settings.get("shrinkToFitWpotd") == "true"
        logger.debug(
            f"Shrink-to-fit={'enabled' if shrink_to_fit else 'disabled'}; "
            f"{'using adaptive loader' if shrink_to_fit else 'downloading original size'}"
        )

        image = self._download_image(
            picurl,
            dimensions=dimensions,
            resize=shrink_to_fit,
        )
        if image is None:
            logger.error("Failed to download WPOTD image")
            raise RuntimeError("Failed to download WPOTD image.")
        if shrink_to_fit:
            logger.info(f"Image resized to fit device dimensions: {max_width}x{max_height}")

        logger.info("=== Wikipedia POTD Plugin: Image generation complete ===")
        return image

    def _determine_date(self, settings: Dict[str, Any]) -> date:
        if settings.get("randomizeWpotd") == "true":
            start = datetime(2015, 1, 1)
            delta_days = (datetime.today() - start).days
            return (start + timedelta(days=randint(0, delta_days))).date()
        elif settings.get("customDate"):
            return datetime.strptime(settings["customDate"], "%Y-%m-%d").date()
        else:
            return datetime.today().date()

    def _download_image(self, url: str, dimensions: tuple = None, resize: bool = False) -> Image.Image:
        """
        Download image from URL, optionally resizing with adaptive loader.

        Args:
            url: Image URL
            dimensions: Target dimensions if resizing
            resize: Whether to use adaptive resizing
        """
        try:
            if url.lower().endswith(".svg"):
                logger.warning("SVG format is not supported by Pillow. Skipping image download.")
                raise RuntimeError("Unsupported image format: SVG.")

            if resize and dimensions:
                # Use adaptive loader for memory-efficient processing
                return self.image_loader.from_url(url, dimensions, timeout_ms=10000, headers=self.HEADERS)
            else:
                # Original behavior: download without resizing
                session = get_http_session()
                response = session.get(url, headers=self.HEADERS, timeout=10)
            response.raise_for_status()
            return Image.open(BytesIO(response.content))

        except UnidentifiedImageError as e:
            logger.error(f"Unsupported image format at {url}: {str(e)}")
            raise RuntimeError("Unsupported image format.")
        except Exception as e:
            logger.error(f"Failed to load WPOTD image from {url}: {str(e)}")
            raise RuntimeError("Failed to load WPOTD image.")

    def _fetch_potd(self, cur_date: date) -> Dict[str, Any]:
        title = f"Template:POTD/{cur_date.isoformat()}"
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "prop": "images",
            "titles": title
        }

        data = self._make_request(params)
        try:
            filename = data["query"]["pages"][0]["images"][0]["title"]
        except (KeyError, IndexError) as e:
            logger.error(f"Failed to retrieve POTD filename for {cur_date}: {e}")
            raise RuntimeError("Failed to retrieve POTD filename.")

        image_src = self._fetch_image_src(filename)

        return {
            "filename": filename,
            "image_src": image_src,
            "image_page_url": f"https://en.wikipedia.org/wiki/{title}",
            "date": cur_date
        }

    def _fetch_image_src(self, filename: str) -> str:
        params = {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url",
            "titles": filename
        }
        data = self._make_request(params)
        try:
            page = next(iter(data["query"]["pages"].values()))
            return page["imageinfo"][0]["url"]
        except (KeyError, IndexError, StopIteration) as e:
            logger.error(f"Failed to retrieve image URL for {filename}: {e}")
            raise RuntimeError("Failed to retrieve image URL.")

    def _make_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            session = get_http_session()
            response = session.get(self.API_URL, params=params, headers=self.HEADERS, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Wikipedia API request failed with params {params}: {str(e)}")
            raise RuntimeError("Wikipedia API request failed.")
