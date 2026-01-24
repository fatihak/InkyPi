import logging
from random import choice, random

import requests
from PIL import Image, ImageColor, ImageOps
from io import BytesIO

from PIL.ImageFile import ImageFile
from plugins.base_plugin.base_plugin import BasePlugin

from utils.image_utils import pad_image_blur

logger = logging.getLogger(__name__)


class ImmichProvider:
    def __init__(self, base_url: str, key: str, orientation: str):
        self.base_url = base_url
        self.key = key
        self.orientation = orientation
        self.headers = {"x-api-key": self.key}

    def get_album_data(self, album_name: str) -> dict:
        r = requests.get(f"{self.base_url}/api/albums", headers=self.headers, timeout=30)
        r.raise_for_status()
        albums = r.json()
        album_summary = [a for a in albums if a["albumName"] == album_name][0]

        if album_summary is None:
            raise RuntimeError(f"Album {album_name} not found.")

        album_id = album_summary["id"]
        r2 = requests.get(f"{self.base_url}/api/albums/{album_id}", headers=self.headers, timeout=30)
        r2.raise_for_status()

        return r2.json()

    def get_asset_ids(self, album_name: str) -> list[str]:
        album = self.get_album_data(album_name)
        return [asset["id"] for asset in album.get("assets", [])]

    def get_image(self, album: str) -> ImageFile | None:
        try:
            logger.info(f"Getting asset IDs for album {album}")
            asset_ids = self.get_asset_ids(album)
        except Exception as e:
            logger.error(f"Error grabbing image from {self.base_url}: {e}")
            return None

        asset_id = choice(asset_ids)

        logger.info(f"Downloading image {asset_id}")
        r = requests.get(f"{self.base_url}/api/assets/{asset_id}/original", headers=self.headers, timeout=30)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content))
        img = ImageOps.exif_transpose(img)
        return img


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
        orientation = device_config.get_config("orientation")
        img = None

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
                img = provider.get_image(album)
                if not img:
                    raise RuntimeError("Failed to load image, please check logs.")

        if img is None:
            raise RuntimeError("Failed to load image, please check logs.")

        if settings.get('padImage') == "true":
            dimensions = device_config.get_resolution()

            if orientation == "vertical":
                dimensions = dimensions[::-1]

            if settings.get('backgroundOption') == "blur":
                return pad_image_blur(img, dimensions)
            else:
                background_color = ImageColor.getcolor(settings.get('backgroundColor') or (255, 255, 255), "RGB")
                return ImageOps.pad(img, dimensions, color=background_color, method=Image.Resampling.LANCZOS)

        return img
