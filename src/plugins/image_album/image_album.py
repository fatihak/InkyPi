import logging
from random import choice, random

import requests
from PIL import Image, ImageColor, ImageOps
from io import BytesIO

from PIL.ImageFile import ImageFile
from plugins.base_plugin.base_plugin import BasePlugin

from src.utils.image_utils import pad_image_blur

logger = logging.getLogger(__name__)

class ImmichProvider:
    def __init__(self, base_url:str, key:str,orientation:str):
        self.base_url = base_url
        self.key = key
        self.orientation = orientation
        self.headers = {"x-api-key": self.key}

    def get_album_id(self, album: str) -> str:
        r = requests.get(f"{self.base_url}/api/albums", headers=self.headers)
        r.raise_for_status()
        albums = r.json()
        album = [a for a in albums if a["albumName"] == album][0]
        return album["id"]

    def get_asset_ids(self, album_id: str) -> list[str]:
        body = {
            "albumIds": [album_id],
            "size": 1000,
            "page": 1
        }
        r2 = requests.post(f"{self.base_url}/api/search/metadata", json=body, headers=self.headers)
        r2.raise_for_status()
        assets_data = r2.json()

        asset_items = assets_data.get("assets", [])["items"]
        return [asset["id"] for asset in asset_items]

    def get_aligned_asset_ids(self, asset_ids: list[str]) ->list[str]:
        aligned_ids = []

        for id in asset_ids:
            asset_url = f"{self.base_url}/api/assets/{id}"
            asset_response = requests.get(asset_url, headers=self.headers)
            asset_response.raise_for_status()
            asset_info = asset_response.json()

            exif = asset_info.get("exifInfo", {})
            width = exif.get("exifImageWidth")
            height = exif.get("exifImageHeight")

            if self.orientation == "horizontal" and width > height:
                aligned_ids.append(id)
            elif self.orientation == "vertical" and width < height:
                aligned_ids.append(id)

        return aligned_ids

    def get_image(self, album:str, settings, repeat=True) -> ImageFile | None:
        try:
            logger.info(f"Getting id for album {album}")
            album_id = self.get_album_id(album)
            logger.info(f"Getting ids from album id {album_id}")
            asset_ids = self.get_asset_ids(album_id)
        except Exception as e:
            logger.error(f"Error grabbing image from {self.base_url}: {e}")
            return None

        prev_images: list = settings.get("prev_images", [])
        asset_ids = [x for x in asset_ids if x not in prev_images]
        asset_ids = self.get_aligned_asset_ids(asset_ids)

        if not repeat and not asset_ids:
            asset_ids = prev_images
            prev_images = []
            settings["prev_images"] = []

        asset_id = choice(asset_ids)

        if not repeat:
            prev_images.append(asset_id)
            settings["prev_images"] = prev_images

        logger.info(f"Downloading image {asset_id}")
        r = requests.get(f"{self.base_url}/api/assets/{asset_id}/original", headers=self.headers)
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
        random = settings.get("randomize", False)
        random_repetition = settings.get("randomRepetition", False)
        orientation = device_config.get_config("orientation")

        match settings.get("albumProvider"):
            case "Immich":
                key = device_config.load_env_key("IMMICH_KEY")
                if not key:
                    raise RuntimeError("Immich API Key not configured.")

                url = settings.get('url')
                if not url:
                    raise RuntimeError("URL is required.")

                album = settings.get('album')
                if not album:
                    raise RuntimeError("Album is required.")

                provider = ImmichProvider(url, key, orientation)
                img = provider.get_image(album, settings, random_repetition)
                if not img:
                    raise RuntimeError("Failed to load image, please check logs.")

        if settings.get("padImage", False):
            dimensions = device_config.get_resolution()

            if orientation == "vertical":
                dimensions = dimensions[::-1]

            if settings.get('blur') == "true":
                return pad_image_blur(img, dimensions)
            else:
                background_color = ImageColor.getcolor(settings.get('backgroundColor') or (255, 255, 255), "RGB")
                return ImageOps.pad(img, dimensions, color=background_color, method=Image.Resampling.LANCZOS)

        return img
