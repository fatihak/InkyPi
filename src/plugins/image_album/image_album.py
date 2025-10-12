import logging
from random import choice, random

import requests
from PIL import Image
from io import BytesIO

from PIL.ImageFile import ImageFile
from plugins.base_plugin.base_plugin import BasePlugin

logger = logging.getLogger(__name__)

class ImmichProvider:
    def get_album_id(self, base: str, album: str, key: str) -> str:
        r = requests.get(f"{base}/albums", headers={"x-api-key": key})
        r.raise_for_status()
        albums = r.json()
        album = [a for a in albums if a["albumName"] == album][0]
        return album["id"]

    def get_asset_ids(self, base: str, album_id: str, key: str) -> list[str]:
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

    def get_image(self, url:str, key:str, album:str, settings) -> ImageFile | None:
        try:
            logger.info(f"Getting id for album {album}")
            album_id = self.get_album_id(url, album, key)
            logger.info(f"Getting ids from album id {album_id}")
            asset_ids = self.get_asset_ids(url, album_id, key)
        except Exception as e:
            logger.error(f"Error grabbing image from {url}: {e}")
            return None

        prev_images: list = settings.get("prev_images", [])
        logger.info(f"Asset ids size {len(asset_ids)}")
        asset_ids = [x for x in asset_ids if x not in prev_images]
        logger.info(f"Asset ids size after {len(asset_ids)}")

        if not asset_ids:
            asset_ids = prev_images
            prev_images = []
            settings["prev_images"] = []

        asset_id = choice(asset_ids)
        prev_images.append(asset_id)
        logger.info(f"Picked image {asset_id}")

        settings["prev_images"] = prev_images

        logger.info(f"Downloading image {asset_id}")
        r = requests.get(f"{url}/assets/{asset_id}/original", headers={"x-api-key": key})
        r.raise_for_status()
        return Image.open(BytesIO(r.content))


class ImageAlbum(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "Immich",
            "expected_key": "IMMICH_KEY"
        }
        return template_params

    def generate_image(self, settings, device_config):
        match settings.get("albumProvider"):
            case "Immich":
                provider = ImmichProvider()

                key = device_config.load_env_key("IMMICH_KEY")
                if not key:
                    raise RuntimeError("Immich API Key not configured.")

                url = settings.get('url')
                if not url:
                    raise RuntimeError("URL is required.")

                album = settings.get('album')
                if not album:
                    raise RuntimeError("Album is required.")

                img = provider.get_image(url, key, album, settings)
                if not img:
                    raise RuntimeError("Failed to load image, please check logs.")


        return img
