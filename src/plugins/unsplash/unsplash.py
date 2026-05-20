from plugins.base_plugin.base_plugin import BasePlugin
from utils.image_loader import _is_low_resource_device
from utils.http_client import get_http_session
import logging
import random
import requests

logger = logging.getLogger(__name__)

class Unsplash(BasePlugin):
    PHOTO_ASSET_TYPE = 'photo'
    ILLUSTRATION_ASSET_TYPE = 'illustration'
    MIXED_ASSET_TYPE = 'mixed'
    COLLECTION_ASSET_TYPES = {PHOTO_ASSET_TYPE, ILLUSTRATION_ASSET_TYPE}

    def generate_image(self, settings, device_config):
        logger.info("=== Unsplash Plugin: Starting image generation ===")

        access_key = device_config.load_env_key("UNSPLASH_ACCESS_KEY")
        if not access_key:
            logger.error("Unsplash Access Key not found in environment")
            raise RuntimeError("'Unsplash Access Key' not found.")

        search_query = settings.get('search_query')
        collections = settings.get('collections')
        content_filter = settings.get('content_filter', 'low')
        color = settings.get('color')
        orientation = settings.get('orientation')
        asset_type = settings.get('asset_type', self.PHOTO_ASSET_TYPE)
        asset_type = (asset_type or self.PHOTO_ASSET_TYPE).strip().lower()

        # Automatically determine image size based on device capabilities
        is_low_resource = _is_low_resource_device()
        image_size = 'regular' if is_low_resource else 'full'
        logger.info(f"Device type: {'low-resource' if is_low_resource else 'standard'}, using image size: '{image_size}'")

        logger.info(f"Settings: image_size='{image_size}', content_filter='{content_filter}', asset_type='{asset_type}'")
        if search_query:
            logger.info(f"Search query: '{search_query}'")
        if collections:
            logger.info(f"Collections: {collections}")
        if color:
            logger.debug(f"Color filter: {color}")
        if orientation:
            logger.debug(f"Orientation: {orientation}")

        if asset_type not in {self.PHOTO_ASSET_TYPE, self.ILLUSTRATION_ASSET_TYPE, self.MIXED_ASSET_TYPE}:
            logger.error(f"Unknown Unsplash asset_type setting: {asset_type}")
            raise RuntimeError("Unknown Unsplash asset type setting.")

        if asset_type in {self.ILLUSTRATION_ASSET_TYPE, self.MIXED_ASSET_TYPE} and search_query:
            logger.error("Search query is only supported for Unsplash photos mode")
            raise RuntimeError("Search query is only supported for Unsplash photos mode.")

        if asset_type in {self.ILLUSTRATION_ASSET_TYPE, self.MIXED_ASSET_TYPE} and not collections:
            logger.error("Collections are required for Unsplash illustration and mixed modes")
            raise RuntimeError("Collections are required for Unsplash illustration and mixed modes.")

        try:
            logger.debug("Fetching image from Unsplash API...")
            session = get_http_session()

            if asset_type == self.PHOTO_ASSET_TYPE:
                selected_item = self._fetch_photo(session, access_key, search_query, collections, content_filter, color, orientation)
            else:
                selected_item = self._fetch_collection_item(session, access_key, collections, orientation, asset_type)

            # Use selected image size (with automatic downgrade for low-RAM devices)
            image_url = self._get_image_url(selected_item, image_size)
            logger.debug(f"Selected Unsplash {self._detect_asset_type(selected_item)} URL")

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching image from Unsplash API: {e}")
            raise RuntimeError("Failed to fetch image from Unsplash API, please check logs.")
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Error parsing Unsplash API response: {e}")
            raise RuntimeError("Failed to parse Unsplash API response, please check logs.")


        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
            logger.debug(f"Vertical orientation detected, dimensions: {dimensions[0]}x{dimensions[1]}")

        logger.info(f"Fetching image (size: {image_size}): {image_url}")

        # Use adaptive image loader for memory-efficient processing
        image = self.image_loader.from_url(image_url, dimensions, timeout_ms=40000)

        if not image:
            logger.error("Failed to load and process image")
            raise RuntimeError("Failed to load image, please check logs.")

        logger.info("=== Unsplash Plugin: Image generation complete ===")
        return image

    def _fetch_photo(self, session, access_key, search_query, collections, content_filter, color, orientation):
        params = {
            'client_id': access_key,
            'content_filter': content_filter,
            'per_page': 100,
        }

        if search_query:
            url = "https://api.unsplash.com/search/photos"
            params['query'] = search_query
            logger.debug(f"Using search endpoint: {url}")
        else:
            url = "https://api.unsplash.com/photos/random"
            logger.debug(f"Using random photo endpoint: {url}")

        if collections:
            params['collections'] = collections
        if color:
            params['color'] = color
        if orientation:
            params['orientation'] = orientation

        response = session.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if not search_query:
            logger.debug("Retrieved random photo")
            return data

        results = data.get("results")
        if not results:
            logger.warning(f"No images found for search query: '{search_query}'")
            raise RuntimeError("No images found for the given search query.")

        logger.info(f"Found {len(results)} images matching search query")
        logger.debug(f"Selected random image from {len(results)} results")
        return random.choice(results)

    def _fetch_collection_item(self, session, access_key, collections, orientation, asset_type):
        collection_ids = [collection_id.strip() for collection_id in collections.split(',') if collection_id.strip()]
        if not collection_ids:
            logger.error("No usable Unsplash collection IDs configured")
            raise RuntimeError("No usable Unsplash collection IDs configured.")

        wanted_asset_types = self.COLLECTION_ASSET_TYPES if asset_type == self.MIXED_ASSET_TYPE else {asset_type}
        candidates = []

        for collection_id in collection_ids:
            url = f"https://api.unsplash.com/collections/{collection_id}/photos"
            params = {
                'client_id': access_key,
                'per_page': 30,
            }
            if orientation:
                params['orientation'] = orientation

            logger.debug(f"Using collection endpoint for {collection_id}: {url}")
            response = session.get(url, params=params)
            response.raise_for_status()
            collection_items = response.json()

            matching_items = [
                item for item in collection_items
                if self._detect_asset_type(item) in wanted_asset_types and item.get('urls')
            ]
            logger.info(f"Found {len(matching_items)} {asset_type} candidates in collection {collection_id}")
            candidates.extend(matching_items)

        if not candidates:
            logger.warning(f"No Unsplash {asset_type} items found in configured collections: {collections}")
            raise RuntimeError(f"No Unsplash {asset_type} items found in the configured collections.")

        logger.info(f"Selected random {asset_type} item from {len(candidates)} collection candidates")
        return random.choice(candidates)

    def _detect_asset_type(self, item):
        asset_type = item.get('asset_type')
        if asset_type:
            return asset_type

        self_link = item.get('links', {}).get('self', '')
        if '/illustrations/' in self_link:
            return self.ILLUSTRATION_ASSET_TYPE

        return self.PHOTO_ASSET_TYPE

    def _get_image_url(self, item, image_size):
        urls = item.get('urls') or {}
        fallback_order = [image_size, 'regular', 'small', 'full', 'raw']

        for key in dict.fromkeys(fallback_order):
            image_url = urls.get(key)
            if image_url:
                return image_url

        raise KeyError(f"No usable image URL found for Unsplash item {item.get('id')}")
