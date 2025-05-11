import random
import requests
import logging
from PIL import Image
from io import BytesIO
from plugins.base_plugin.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

class Immich(BasePlugin):
    def generate_image(self, settings, device_config):
        api_url = settings.get("api_url")  # e.g., "http://your-immich-server/api"
        album_id = settings.get("album_id")  # ID of the album to fetch images from
        api_key = device_config.load_env_key("IMMICH_API_KEY")  # API key for authentication

        if not api_url or not album_id or not api_key:
            raise RuntimeError("API URL, Album ID, and API Key must be configured in plugin settings.")

        # Fetch image list from Immich API
        headers = {"x-api-key": api_key}
        response = requests.get(f"{api_url}/albums/{album_id}", headers=headers)

        if response.status_code != 200:
            raise RuntimeError(f"Failed to fetch images: {response.status_code}")

        assets = response.json().get("assets", [])
        if not assets:
            raise RuntimeError("No images found in the selected album.")

        # Get the first image (or random image if desired)
        selected_asset = random.choice(assets)
        logger.info(f"Selected image: {selected_asset['id']}")
        image_url = f"{api_url}/assets/{selected_asset['id']}/original"
        image_response = requests.get(image_url, headers=headers)

        if image_response.status_code != 200:
            raise RuntimeError("Failed to download image.")

        img = Image.open(BytesIO(image_response.content))

        # Resize image to fit the display
        #width, height = device_config.get_resolution()
        #img = img.convert("L").resize((width, height))

        return img
