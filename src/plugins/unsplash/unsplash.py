from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
from io import BytesIO
import requests
import logging
import random
import gc
import psutil

logger = logging.getLogger(__name__)

def _is_low_resource_device():
    """
    Detect if running on a low-resource device (e.g., Raspberry Pi Zero).
    Returns True if device has less than 1GB RAM, False otherwise.
    """
    try:
        total_memory_gb = psutil.virtual_memory().total / (1024 ** 3)
        is_low_resource = total_memory_gb < 1.0
        logger.debug(f"Device RAM: {total_memory_gb:.2f}GB - Low resource mode: {is_low_resource}")
        return is_low_resource
    except Exception as e:
        # If we can't detect, assume low resource to be safe
        logger.warning(f"Could not detect device memory: {e}. Defaulting to low-resource mode.")
        return True

def grab_image(image_url, dimensions, timeout_ms=40000):
    """
    Grab an image from a URL and resize it to the specified dimensions.
    Automatically optimizes for device capabilities - uses memory-efficient
    methods on low-RAM devices and maximum quality on powerful devices.
    """
    is_low_resource = _is_low_resource_device()

    try:
        logger.debug(f"Downloading image from {image_url}")
        logger.debug(f"Target dimensions: {dimensions[0]}x{dimensions[1]}")

        # Stream the download to avoid loading entire file into memory at once
        response = requests.get(image_url, timeout=timeout_ms / 1000, stream=True)
        response.raise_for_status()

        # Load image from streamed response
        img = Image.open(BytesIO(response.content))
        original_size = img.size
        original_pixels = original_size[0] * original_size[1]
        logger.info(f"Downloaded image: {original_size[0]}x{original_size[1]} ({img.mode} mode, {original_pixels/1_000_000:.1f}MP)")

        # Convert to RGB if necessary (removes alpha channel, saves memory)
        # E-ink displays don't need alpha channel anyway
        if img.mode in ('RGBA', 'LA', 'P'):
            logger.debug(f"Converting image from {img.mode} to RGB")
            img = img.convert('RGB')

        # Choose resampling filter based on device capabilities
        if is_low_resource:
            # On low-resource devices: use BICUBIC for faster processing
            # Quality difference is imperceptible on e-ink displays
            quality_filter = Image.BICUBIC
            use_two_stage = True
            logger.debug("Using memory-efficient processing (BICUBIC filter)")
        else:
            # On powerful devices: use LANCZOS for maximum quality
            quality_filter = Image.LANCZOS
            use_two_stage = False  # Single-pass resize, no need to optimize
            logger.debug("Using high-quality processing (LANCZOS filter)")

        # For very large images on low-resource devices, use aggressive two-stage resize
        # Use thumbnail() which is more memory efficient than resize()
        if use_two_stage and (img.size[0] > dimensions[0] * 2 or img.size[1] > dimensions[1] * 2):
            logger.debug(f"Image is {img.size[0]}x{img.size[1]}, using two-stage resize for memory efficiency")

            # First pass: Aggressive downsample using thumbnail (in-place modification, very memory efficient)
            # Calculate intermediate size that maintains aspect ratio
            aspect = img.size[0] / img.size[1]
            if aspect > 1:  # Landscape
                intermediate_size = (dimensions[0] * 2, int(dimensions[0] * 2 / aspect))
            else:  # Portrait
                intermediate_size = (int(dimensions[1] * 2 * aspect), dimensions[1] * 2)

            logger.debug(f"Stage 1: Downsampling to ~{intermediate_size[0]}x{intermediate_size[1]} using NEAREST")
            # thumbnail() modifies in-place and is MUCH more memory efficient
            img.thumbnail(intermediate_size, Image.NEAREST)
            logger.debug(f"Stage 1 complete: {img.size[0]}x{img.size[1]}")
            gc.collect()  # Force garbage collection after first stage

            # Second pass: high-quality resize to exact dimensions
            logger.debug(f"Stage 2: Final resize to {dimensions[0]}x{dimensions[1]} using LANCZOS")
            img = img.resize(dimensions, Image.LANCZOS)
            logger.debug(f"Stage 2 complete: {dimensions[0]}x{dimensions[1]}")
        else:
            # Standard resize with appropriate quality filter
            logger.debug(f"Resizing directly from {img.size[0]}x{img.size[1]} to {dimensions[0]}x{dimensions[1]}")
            img = img.resize(dimensions, quality_filter)

        # Explicit garbage collection on low-resource devices
        if is_low_resource:
            gc.collect()
            logger.debug("Garbage collection completed")

        logger.info(f"Image processing complete: {dimensions[0]}x{dimensions[1]}")
        return img
    except MemoryError as e:
        logger.error(f"Out of memory while processing image from {image_url}: {e}")
        logger.error("Try using a smaller image size setting (Small or Regular instead of Full/Raw)")
        gc.collect()  # Try to free memory
        return None
    except Exception as e:
        logger.error(f"Error grabbing image from {image_url}: {e}")
        return None

class Unsplash(BasePlugin):
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
        image_size = settings.get('image_size', 'regular')  # Default to 'regular' for memory efficiency

        # CRITICAL: Automatically downgrade dangerous image sizes on low-resource devices
        # This prevents OOM crashes
        is_low_resource = _is_low_resource_device()
        original_size = image_size

        if is_low_resource and image_size == 'full':
            image_size = 'regular'
            logger.warning(f"⚠️  Image size 'full' may cause crashes on low-RAM devices")
            logger.warning(f"⚠️  Automatically downgraded from '{original_size}' to '{image_size}' for stability")

        logger.info(f"Settings: image_size='{image_size}', content_filter='{content_filter}'")
        if search_query:
            logger.info(f"Search query: '{search_query}'")
        if collections:
            logger.info(f"Collections: {collections}")
        if color:
            logger.debug(f"Color filter: {color}")
        if orientation:
            logger.debug(f"Orientation: {orientation}")

        params = {
            'client_id': access_key,
            'content_filter': content_filter,
            'per_page': 100,
        }

        if search_query:
            url = f"https://api.unsplash.com/search/photos"
            params['query'] = search_query
            logger.debug(f"Using search endpoint: {url}")
        else:
            url = f"https://api.unsplash.com/photos/random"
            logger.debug(f"Using random photo endpoint: {url}")

        if collections:
            params['collections'] = collections
        if color:
            params['color'] = color
        if orientation:
            params['orientation'] = orientation

        try:
            logger.debug("Fetching image from Unsplash API...")
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if search_query:
                results = data.get("results")
                if not results:
                    logger.warning(f"No images found for search query: '{search_query}'")
                    raise RuntimeError("No images found for the given search query.")
                logger.info(f"Found {len(results)} images matching search query")
                # Use selected image size (with automatic downgrade for low-RAM devices)
                selected_photo = random.choice(results)
                image_url = selected_photo["urls"][image_size]
                logger.debug(f"Selected random image from {len(results)} results")
            else:
                # Use selected image size (with automatic downgrade for low-RAM devices)
                image_url = data["urls"][image_size]
                logger.debug("Retrieved random image URL")

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching image from Unsplash API: {e}")
            raise RuntimeError("Failed to fetch image from Unsplash API, please check logs.")
        except (KeyError, IndexError) as e:
            logger.error(f"Error parsing Unsplash API response: {e}")
            raise RuntimeError("Failed to parse Unsplash API response, please check logs.")


        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
            logger.debug(f"Vertical orientation detected, dimensions: {dimensions[0]}x{dimensions[1]}")

        logger.info(f"Fetching image (size: {image_size}): {image_url}")

        image = grab_image(image_url, dimensions, timeout_ms=40000)

        if not image:
            logger.error("Failed to load and process image")
            raise RuntimeError("Failed to load image, please check logs.")

        logger.info("=== Unsplash Plugin: Image generation complete ===")
        return image
