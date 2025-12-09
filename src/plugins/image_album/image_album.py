import logging
from random import choice

from PIL import Image, ImageColor, ImageOps
from utils.http_client import get_http_session
from plugins.base_plugin.base_plugin import BasePlugin
from utils.image_utils import pad_image_blur, resize_image

logger = logging.getLogger(__name__)


class ImmichProvider:
    def __init__(self, base_url: str, key: str, image_loader):
        self.base_url = base_url
        self.key = key
        self.headers = {"x-api-key": self.key}
        self.image_loader = image_loader
        self.session = get_http_session()

    def get_album_id(self, album: str) -> str:
        logger.debug(f"Fetching albums from {self.base_url}")
        r = self.session.get(f"{self.base_url}/api/albums", headers=self.headers)
        r.raise_for_status()
        albums = r.json()

        matching_albums = [a for a in albums if a["albumName"] == album]
        if not matching_albums:
            raise RuntimeError(f"Album '{album}' not found.")

        return matching_albums[0]["id"]

    def get_assets(self, album_id: str) -> list[dict]:
        """Fetch all assets from album with their full metadata including dimensions."""
        all_items = []
        page_items = [1]
        page = 1

        logger.debug(f"Fetching assets from album {album_id}")
        while page_items:
            body = {
                "albumIds": [album_id],
                "size": 1000,
                "page": page
            }
            r2 = self.session.post(f"{self.base_url}/api/search/metadata", json=body, headers=self.headers)
            r2.raise_for_status()
            assets_data = r2.json()

            page_items = assets_data.get("assets", {}).get("items", [])
            all_items.extend(page_items)
            page += 1

        logger.debug(f"Found {len(all_items)} total assets in album")

        # Fetch full asset details to get exifInfo with dimensions
        # The search/metadata endpoint doesn't include dimension data
        logger.debug(f"Fetching full details for {len(all_items)} assets to get dimensions")
        detailed_assets = []

        for asset in all_items:
            asset_id = asset.get('id')
            try:
                r = self.session.get(f"{self.base_url}/api/assets/{asset_id}", headers=self.headers)
                r.raise_for_status()
                detailed_asset = r.json()
                detailed_assets.append(detailed_asset)
            except Exception as e:
                logger.warning(f"Failed to fetch details for asset {asset_id}: {e}")
                # Keep the original asset data even if detail fetch fails
                detailed_assets.append(asset)

        # Debug: Log first detailed asset structure
        if detailed_assets:
            first_asset = detailed_assets[0]
            logger.debug(f"Sample detailed asset - ID: {first_asset.get('id')}")
            logger.debug(f"Available keys: {list(first_asset.keys())}")
            if 'exifInfo' in first_asset:
                exif_keys = list(first_asset['exifInfo'].keys())
                logger.debug(f"EXIF keys: {exif_keys}")
                exif_info = first_asset['exifInfo']
                if 'exifImageWidth' in exif_info and 'exifImageHeight' in exif_info:
                    logger.debug(f"Dimensions: {exif_info['exifImageWidth']}x{exif_info['exifImageHeight']}")

        return detailed_assets

    def filter_assets_by_orientation(self, assets: list[dict], dimensions: tuple[int, int]) -> list[dict]:
        """
        Filter assets to match display orientation.

        Args:
            assets: List of asset objects with dimension metadata
            dimensions: Target display dimensions (width, height)

        Returns:
            List of assets matching the orientation, raises error if none match
        """
        display_width, display_height = dimensions
        display_is_landscape = display_width > display_height
        orientation_name = "landscape" if display_is_landscape else "portrait"

        logger.info(f"Display: {display_width}x{display_height} ({orientation_name})")

        matching_assets = []
        skipped_wrong_orientation = 0
        skipped_no_dimensions = 0

        for asset in assets:
            asset_id = asset.get("id", "unknown")

            # Get EXIF info
            exif_info = asset.get("exifInfo", {})
            img_width = exif_info.get("exifImageWidth")
            img_height = exif_info.get("exifImageHeight")
            exif_orientation = exif_info.get("orientation")

            # Skip assets without dimension info
            if not img_width or not img_height:
                logger.debug(f"Asset {asset_id}: No dimensions available, skipping")
                skipped_no_dimensions += 1
                continue

            # Log orientation value for debugging
            logger.debug(f"Asset {asset_id}: EXIF dimensions {img_width}x{img_height}, orientation={exif_orientation} (type: {type(exif_orientation).__name__})")

            # Apply EXIF orientation to determine actual displayed dimensions
            # EXIF orientation values that cause 90°/270° rotation (swaps dimensions):
            # - 6: Rotate 90° CW
            # - 8: Rotate 270° CW (or 90° CCW)
            # The value might be int or string depending on Immich version
            actual_width = img_width
            actual_height = img_height

            orientation_rotates = False
            if exif_orientation is not None:
                # Convert to int if it's a string
                try:
                    orientation_value = int(exif_orientation) if isinstance(exif_orientation, str) else exif_orientation
                    if orientation_value in [6, 8]:
                        orientation_rotates = True
                except (ValueError, TypeError):
                    logger.debug(f"Asset {asset_id}: Could not parse orientation value: {exif_orientation}")

            if orientation_rotates:
                # Image will be rotated 90° or 270°, swap dimensions
                actual_width = img_height
                actual_height = img_width
                logger.debug(f"Asset {asset_id}: Orientation {exif_orientation} causes rotation - swapping to {actual_width}x{actual_height}")

            # Check if asset orientation matches display orientation
            asset_is_landscape = actual_width > actual_height
            asset_orientation = "landscape" if asset_is_landscape else "portrait"

            dimension_info = f"{img_width}x{img_height}"
            if orientation_rotates:
                dimension_info += f" (rotated to {actual_width}x{actual_height})"

            if asset_is_landscape == display_is_landscape:
                logger.debug(f"Asset {asset_id}: {dimension_info} ({asset_orientation}) - MATCH")
                matching_assets.append(asset)
            else:
                logger.debug(f"Asset {asset_id}: {dimension_info} ({asset_orientation}) - FILTERED OUT")
                skipped_wrong_orientation += 1

        logger.info(f"Orientation filter results: {len(matching_assets)} matching, "
                   f"{skipped_wrong_orientation} wrong orientation, {skipped_no_dimensions} no dimension data")

        if matching_assets:
            logger.info(f"Using {len(matching_assets)} {orientation_name} images")
            return matching_assets
        else:
            if skipped_no_dimensions > 0:
                error_msg = (f"No {orientation_name} images found in album. "
                           f"Found {len(assets)} total assets but {skipped_no_dimensions} have no dimension metadata. "
                           f"Try disabling orientation filtering or check your Immich version.")
            else:
                error_msg = f"No {orientation_name} images found in album. Found {len(assets)} total assets but none match the display orientation."
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def get_image(self, album: str, dimensions: tuple[int, int], orientation_filter: bool = True) -> Image.Image | None:
        """
        Get a random image from the album, optionally filtered by orientation.

        Args:
            album: Album name
            dimensions: Target dimensions (width, height)
            orientation_filter: If True, prefer images matching the display orientation

        Returns:
            PIL Image or None on error
        """
        try:
            logger.info(f"Getting id for album '{album}'")
            album_id = self.get_album_id(album)
            logger.info(f"Getting assets from album id {album_id}")
            assets = self.get_assets(album_id)

            if not assets:
                logger.error(f"No assets found in album '{album}'")
                return None

            # Filter by orientation if enabled
            if orientation_filter:
                assets = self.filter_assets_by_orientation(assets, dimensions)

                if not assets:
                    logger.error(f"No assets available after filtering")
                    return None

        except Exception as e:
            logger.error(f"Error retrieving album data from {self.base_url}: {e}")
            return None

        # Select random asset from (filtered) list
        selected_asset = choice(assets)
        asset_id = selected_asset["id"]
        asset_url = f"{self.base_url}/api/assets/{asset_id}/original"

        logger.info(f"Selected random asset: {asset_id}")
        logger.debug(f"Downloading from: {asset_url}")

        # Use adaptive image loader for memory-efficient processing
        # Don't auto-resize since we need to handle padding options later
        img = self.image_loader.from_url(
            asset_url,
            dimensions,
            timeout_ms=40000,
            resize=False,
            headers=self.headers
        )

        if not img:
            logger.error(f"Failed to load image {asset_id} from Immich")
            return None

        logger.info(f"Successfully loaded image: {img.size[0]}x{img.size[1]}")
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
        logger.info("=== Image Album Plugin: Starting image generation ===")

        orientation = device_config.get_config("orientation")
        dimensions = device_config.get_resolution()

        if orientation == "vertical":
            dimensions = dimensions[::-1]
            logger.debug(f"Vertical orientation detected, dimensions: {dimensions[0]}x{dimensions[1]}")

        img = None
        album_provider = settings.get("albumProvider")
        logger.info(f"Album provider: {album_provider}")

        match album_provider:
            case "Immich":
                key = device_config.load_env_key("IMMICH_KEY")
                if not key:
                    logger.error("Immich API Key not configured")
                    raise RuntimeError("Immich API Key not configured.")

                url = settings.get('url')
                if not url:
                    logger.error("Immich URL not provided")
                    raise RuntimeError("Immich URL is required.")

                album = settings.get('album')
                if not album:
                    logger.error("Album name not provided")
                    raise RuntimeError("Album name is required.")

                logger.info(f"Immich URL: {url}")
                logger.info(f"Album: {album}")

                # Check if orientation filtering is enabled (default: true)
                orientation_filter_setting = settings.get('orientationFilter', 'true')
                orientation_filter = orientation_filter_setting == 'true'
                logger.info(f"Orientation filter setting received: '{orientation_filter_setting}'")
                logger.info(f"Orientation filtering: {'enabled' if orientation_filter else 'disabled'}")

                provider = ImmichProvider(url, key, self.image_loader)
                img = provider.get_image(album, dimensions, orientation_filter)

                if not img:
                    logger.error("Failed to retrieve image from Immich")
                    raise RuntimeError("Failed to load image, please check logs.")
            case _:
                logger.error(f"Unknown album provider: {album_provider}")
                raise RuntimeError(f"Unsupported album provider: {album_provider}")

        if img is None:
            logger.error("Image is None after provider processing")
            raise RuntimeError("Failed to load image, please check logs.")

        # Check padding options
        use_padding = settings.get('padImage') == "true"
        background_option = settings.get('backgroundOption', 'blur')
        logger.debug(f"Settings: pad_image={use_padding}, background_option={background_option}, orientation_filter={orientation_filter}")

        # When orientation filtering is enabled and found a matching image,
        # use crop-to-fill instead of pad-to-fit for better display
        if orientation_filter and use_padding:
            logger.info("Orientation-matched image: using crop-to-fill instead of pad-to-fit for optimal display")
            img = resize_image(img, dimensions)
        elif use_padding:
            logger.debug(f"Applying padding with {background_option} background")
            if background_option == "blur":
                img = pad_image_blur(img, dimensions)
            else:
                background_color = ImageColor.getcolor(
                    settings.get('backgroundColor') or "#ffffff",
                    "RGB"
                )
                img = ImageOps.pad(img, dimensions, color=background_color, method=Image.Resampling.LANCZOS)
        else:
            # No padding requested, resize to fit dimensions
            logger.debug(f"Resizing to fit dimensions: {dimensions[0]}x{dimensions[1]}")
            img = img.resize(dimensions, Image.LANCZOS)

        logger.info("=== Image Album Plugin: Image generation complete ===")
        return img
