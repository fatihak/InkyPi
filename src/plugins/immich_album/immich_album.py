import logging
from random import choice

import requests
from PIL import Image
from io import BytesIO
from plugins.base_plugin.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

def get_album_id(base: str, album:str, key:str) -> str:
    r = requests.get(f"{base}/albums", headers={"x-api-key": key})
    r.raise_for_status()
    albums = r.json()
    album = [a for a in albums if a["albumName"] == album][0]
    return album["id"]

def get_asset_ids(base: str, album_id: str, key:str) -> list[str]:
    body = {
        "albumIds": [album_id],
        "size": 1000,
        "page": 1
    }
    r2 = requests.post(f"{base}/search/metadata", json=body, headers={"x-api-key": key})
    r2.raise_for_status()
    assets_data = r2.json()

    asset_items = assets_data.get("assets", [])["items"]
    return [asset["id"] for asset in asset_items]

class ImmichAlbum(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "Immich",
            "expected_key": "IMMICH_KEY"
        }
        return template_params

    def generate_image(self, settings, device_config):
        key = device_config.load_env_key("IMMICH_KEY")
        if not key:
            raise RuntimeError("Immich API Key not configured.")

        url = settings.get('url')

        if not url:
            raise RuntimeError("URL is required.")

        album = settings.get('album')
        if not album:
            raise RuntimeError("Album is required.")

        try:
            album_id = get_album_id(url, album, key)
            asset_ids = get_asset_ids(url, album_id, key)
        except Exception as e:
            logger.error(f"Error grabbing image from {url}: {e}")
            return None

        asset_id = choice(asset_ids)
        logger.info(f"Picked image {asset_id}")
        r = requests.get(f"{url}/assets/{asset_id}/original", headers={"x-api-key": key})
        r.raise_for_status()
        img = Image.open(BytesIO(r.content))

        if not img:
            raise RuntimeError("Failed to load image, please check logs.")

        return img