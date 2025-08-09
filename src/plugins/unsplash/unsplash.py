from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
from io import BytesIO
import requests
import logging
import random

logger = logging.getLogger(__name__)

def grab_image(image_url, dimensions, timeout_ms=40000):
    """Grab an image from a URL and resize it to the specified dimensions."""
    try:
        response = requests.get(image_url, timeout=timeout_ms / 1000)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))
        img = img.resize(dimensions, Image.LANCZOS)
        return img
    except Exception as e:
        logger.error(f"Error grabbing image from {image_url}: {e}")
        return None

class Unsplash(BasePlugin):
    def generate_image(self, settings, device_config):
        access_key = device_config.load_env_key("UNSPLASH_ACCESS_KEY")
        if not access_key:
            raise RuntimeError("'Unsplash Access Key' not found.")

        search_query = settings.get('search_query')
        collections = settings.get('collections')
        content_filter = settings.get('content_filter', 'low')
        color = settings.get('color')
        orientation = settings.get('orientation')
        
        params = {
            'client_id': access_key,
            'content_filter': content_filter,
            'per_page': 100,
        }

        if search_query:
            url = f"https://api.unsplash.com/search/photos"
            params['query'] = search_query
        else:
            url = f"https://api.unsplash.com/photos/random"

        if collections:
            params['collections'] = collections
        if color:
            params['color'] = color
        if orientation:
            params['orientation'] = orientation

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if search_query:
                results = data.get("results")
                if not results:
                    raise RuntimeError("No images found for the given search query.")
                image_url = random.choice(results)["urls"]["full"]
            else:
                image_url = data["urls"]["full"]
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching image from Unsplash API: {e}")
            raise RuntimeError("Failed to fetch image from Unsplash API, please check logs.")
        except (KeyError, IndexError) as e:
            logger.error(f"Error parsing Unsplash API response: {e}")
            raise RuntimeError("Failed to parse Unsplash API response, please check logs.")


        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        logger.info(f"Grabbing image from: {image_url}")

        image = grab_image(image_url, dimensions, timeout_ms=40000)

        if not image:
            raise RuntimeError("Failed to load image, please check logs.")

        return image
