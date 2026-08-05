import json
import logging
import random
import re
from urllib.parse import urlparse

import requests
from PIL import Image, ImageColor, ImageOps

from plugins.base_plugin.base_plugin import BasePlugin
from utils.http_client import get_http_session
from utils.image_utils import pad_image_blur

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 30
IMAGE_TIMEOUT_MS = 40000
VIEWED_PHOTOS_KEY = "_viewedPhotos"
ICLOUD_HEADERS = {"Content-Type": "text/plain"}
BASE62_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def base62_decode(value: str) -> int:
    """Decode an iCloud base62 partition identifier."""
    if not value:
        raise ValueError("The base62 value cannot be empty.")

    decoded = 0
    for character in value:
        try:
            digit = BASE62_ALPHABET.index(character)
        except ValueError as exc:
            raise ValueError(f"Invalid base62 character: {character}") from exc
        decoded = decoded * 62 + digit
    return decoded


def get_stream_id(album_url: str) -> str:
    """Extract and validate the stream ID from an iCloud Shared Album URL."""
    parsed = urlparse(album_url)
    valid_path = parsed.path.rstrip("/") == "/sharedalbum"
    stream_id = parsed.fragment.strip()

    if parsed.scheme != "https" or parsed.hostname != "www.icloud.com" or not valid_path:
        raise RuntimeError(
            "Please provide a full iCloud Shared Album URL, for example "
            "https://www.icloud.com/sharedalbum/#B2D..."
        )

    if not stream_id or not re.fullmatch(r"[A-Za-z0-9]+", stream_id):
        raise RuntimeError("The iCloud Shared Album ID is missing or invalid.")

    return stream_id


def get_partition(stream_id: str) -> int:
    """Calculate the iCloud server partition for a stream ID."""
    if len(stream_id) < 2 or (not stream_id.startswith("A") and len(stream_id) < 3):
        raise RuntimeError("The iCloud Shared Album ID is too short.")

    encoded_partition = stream_id[1] if stream_id.startswith("A") else stream_id[1:3]
    try:
        return base62_decode(encoded_partition)
    except ValueError as exc:
        raise RuntimeError("The iCloud Shared Album partition is invalid.") from exc


class ICloudSharedAlbumProvider:
    """Retrieve metadata and images from an iCloud Shared Album."""

    def __init__(self, image_loader, session=None):
        self.image_loader = image_loader
        self.session = session or get_http_session()

    @staticmethod
    def _endpoint(stream_id: str, operation: str) -> str:
        partition = get_partition(stream_id)
        return (
            f"https://p{partition}-sharedstreams.icloud.com/"
            f"{stream_id}/sharedstreams/{operation}"
        )

    def _post_json(self, stream_id: str, operation: str, payload: dict, error_message: str) -> dict:
        try:
            response = self.session.post(
                self._endpoint(stream_id, operation),
                data=json.dumps(payload),
                headers=ICLOUD_HEADERS,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(error_message) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError("iCloud returned an invalid response.") from exc

        if not isinstance(data, dict):
            raise RuntimeError("iCloud returned an unexpected response.")
        return data

    @staticmethod
    def _largest_derivative(derivatives: dict) -> str | None:
        candidates = []
        for derivative in derivatives.values():
            if not isinstance(derivative, dict) or not derivative.get("checksum"):
                continue
            try:
                width = int(derivative.get("width", 0))
                height = int(derivative.get("height", 0))
            except (TypeError, ValueError):
                continue
            if width > 0 and height > 0:
                candidates.append((width * height, derivative["checksum"]))

        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate[0])[1]

    def get_photos(self, stream_id: str) -> dict[str, str]:
        """Return the best derivative checksum for each usable photo."""
        data = self._post_json(
            stream_id,
            "webstream",
            {"streamCtag": None},
            "Unable to retrieve the iCloud Shared Album.",
        )

        photos = {}
        for photo in data.get("photos") or []:
            if not isinstance(photo, dict):
                continue
            guid = photo.get("photoGuid")
            derivatives = photo.get("derivatives")
            if not guid or not isinstance(derivatives, dict):
                continue
            checksum = self._largest_derivative(derivatives)
            if checksum:
                photos[guid] = checksum

        if not photos:
            raise RuntimeError("No usable photos were found in the iCloud Shared Album.")

        logger.info("Found %d usable photos in the iCloud Shared Album", len(photos))
        return photos

    def get_photo_url(self, stream_id: str, guid: str, checksum: str) -> str:
        """Resolve the temporary download URL for a photo derivative."""
        data = self._post_json(
            stream_id,
            "webasseturls",
            {"photoGuids": [guid]},
            "Unable to retrieve the selected photo from iCloud.",
        )

        items = data.get("items") or {}
        item = items.get(checksum) if isinstance(items, dict) else None
        if not isinstance(item, dict):
            raise RuntimeError("iCloud did not return a download location for the selected photo.")

        location_name = item.get("url_location")
        url_path = item.get("url_path")
        locations = data.get("locations") or {}
        location = locations.get(location_name, {}) if isinstance(locations, dict) else {}

        if not location_name or not isinstance(url_path, str) or not url_path.startswith("/"):
            raise RuntimeError("iCloud returned an invalid photo download location.")

        scheme = str(location.get("scheme", "https")).rstrip(":/")
        if scheme != "https":
            raise RuntimeError("iCloud returned an insecure photo download location.")

        hosts = location.get("hosts") or [location_name]
        if not isinstance(hosts, list):
            hosts = [location_name]
        hosts = [host for host in hosts if isinstance(host, str) and host]
        if not hosts:
            raise RuntimeError("iCloud did not return a valid photo download host.")

        return f"https://{random.choice(hosts)}{url_path}"

    def load_photo(
        self,
        stream_id: str,
        guid: str,
        checksum: str,
        dimensions: tuple[int, int],
        resize: bool,
    ) -> Image.Image:
        photo_url = self.get_photo_url(stream_id, guid, checksum)
        image = self.image_loader.from_url(
            photo_url,
            dimensions,
            timeout_ms=IMAGE_TIMEOUT_MS,
            resize=resize,
        )
        if image is None:
            raise RuntimeError("The selected iCloud photo could not be downloaded or decoded.")
        return image


class ICloudPhotos(BasePlugin):
    """Display photos from an iCloud Shared Album without repeating them."""

    @staticmethod
    def _display_dimensions(device_config) -> tuple[int, int]:
        dimensions = tuple(device_config.get_resolution())
        if device_config.get_config("orientation") == "vertical":
            return dimensions[::-1]
        return dimensions

    @staticmethod
    def _select_photo(settings: dict, current_photos: dict[str, str]) -> tuple[str, str, dict[str, str]]:
        stored_viewed = settings.get(VIEWED_PHOTOS_KEY)
        if not isinstance(stored_viewed, dict):
            stored_viewed = {}

        viewed = {
            guid: checksum
            for guid, checksum in stored_viewed.items()
            if current_photos.get(guid) == checksum
        }
        unseen = [
            guid
            for guid, checksum in current_photos.items()
            if viewed.get(guid) != checksum
        ]

        if not unseen:
            logger.info("All iCloud photos have been viewed; starting a new cycle")
            viewed = {}
            unseen = list(current_photos)

        guid = random.choice(unseen)
        return guid, current_photos[guid], viewed

    def generate_image(self, settings, device_config):
        album_url = (settings.get("album_url") or "").strip()
        if not album_url:
            raise RuntimeError("An iCloud Shared Album URL is required.")

        stream_id = get_stream_id(album_url)
        dimensions = self._display_dimensions(device_config)
        use_padding = settings.get("padImage") == "true"
        background_option = settings.get("backgroundOption", "blur")

        provider = ICloudSharedAlbumProvider(self.image_loader)
        current_photos = provider.get_photos(stream_id)
        guid, checksum, viewed = self._select_photo(settings, current_photos)

        logger.info(
            "Selected one of %d unviewed iCloud photos for a %dx%d display",
            len(current_photos) - len(viewed),
            dimensions[0],
            dimensions[1],
        )
        image = provider.load_photo(
            stream_id,
            guid,
            checksum,
            dimensions,
            resize=not use_padding,
        )

        if use_padding:
            if background_option == "blur":
                image = pad_image_blur(image, dimensions)
            else:
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                background_color = ImageColor.getcolor(
                    settings.get("backgroundColor") or "#ffffff",
                    image.mode,
                )
                image = ImageOps.pad(
                    image,
                    dimensions,
                    color=background_color,
                    method=Image.Resampling.LANCZOS,
                )

        # Persist selection state only after the image has loaded and rendered successfully.
        viewed[guid] = checksum
        settings[VIEWED_PHOTOS_KEY] = viewed
        return image
