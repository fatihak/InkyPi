"""
Adaptive Image Loader for InkyPi
Centralized image loading and processing with device-aware optimizations.

Automatically uses memory-efficient strategies on low-RAM devices (Pi Zero)
and high-performance strategies on capable devices (Pi 3/4).
"""

from PIL import Image, ImageColor, ImageOps
from io import BytesIO
from utils.http_client import get_http_session
from utils.image_utils import pad_image_blur
from utils.settings_migrations import IMAGE_FIT_MODES
import logging
import gc
import psutil
import tempfile
import os

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


class AdaptiveImageLoader:
    """
    Centralized image loading with device-adaptive optimizations.

    Features:
    - Automatic device detection (low-resource vs high-performance)
    - Memory-efficient loading using temp files + PIL draft mode on Pi Zero
    - Fast in-memory loading on powerful devices
    - Automatic resizing with quality-appropriate filters
    - RGB conversion for e-ink compatibility
    - Comprehensive error handling and logging

    Usage:
        loader = AdaptiveImageLoader()
        image = loader.from_url("https://...", (800, 480))
        image = loader.from_file("/path/to/image.jpg", (800, 480))
    """

    # Default headers to avoid 403 errors from sites that block requests without User-Agent
    DEFAULT_HEADERS = {
        'User-Agent': 'InkyPi/1.0 (https://github.com/fatihak/InkyPi/) Python-requests'
    }

    def __init__(self):
        self.is_low_resource = _is_low_resource_device()

    def from_url(
        self,
        url,
        dimensions,
        timeout_ms=40000,
        resize=True,
        headers=None,
        *,
        fit_mode=None,
        background_option="blur",
        background_color="white",
    ):
        """
        Load an image from a URL and optionally resize it.

        Args:
            url: Image URL to download
            dimensions: Target dimensions as (width, height)
            timeout_ms: Request timeout in milliseconds
            resize: Whether to resize the image (default True)
            headers: Optional dict of HTTP headers to include in request
            fit_mode: Optional cover, contain, or auto fitting mode. When set,
                this takes precedence over resize.
            background_option: Background style for contained images (blur or color)
            background_color: Background color when background_option is color

        Returns:
            PIL Image object resized to dimensions, or None on error
        """
        logger.debug(f"Loading image from URL: {url}")
        fit_options = self._resolve_fit_options(
            resize, fit_mode, background_option, background_color
        )

        return self._load_from_url(
            url,
            dimensions,
            timeout_ms,
            headers,
            fit_options,
            use_temp_file=self.is_low_resource,
        )

    def from_file(
        self,
        path,
        dimensions,
        resize=True,
        *,
        fit_mode=None,
        background_option="blur",
        background_color="white",
    ):
        """
        Load an image from a local file and optionally resize it.

        Args:
            path: Path to local image file
            dimensions: Target dimensions as (width, height)
            resize: Whether to resize the image (default True)
            fit_mode: Optional cover, contain, or auto fitting mode. When set,
                this takes precedence over resize.
            background_option: Background style for contained images (blur or color)
            background_color: Background color when background_option is color

        Returns:
            PIL Image object resized to dimensions, or None on error
        """
        logger.debug(f"Loading image from file: {path}")

        if not os.path.exists(path):
            logger.error(f"File not found: {path}")
            return None

        fit_options = self._resolve_fit_options(
            resize, fit_mode, background_option, background_color
        )
        return self._load_from_file(
            path, dimensions, fit_options, use_draft=self.is_low_resource
        )

    def from_bytesio(
        self,
        data,
        dimensions,
        resize=True,
        *,
        fit_mode=None,
        background_option="blur",
        background_color="white",
    ):
        """
        Load an image from BytesIO object and optionally resize it.

        Args:
            data: BytesIO object containing image data
            dimensions: Target dimensions as (width, height)
            resize: Whether to resize the image (default True)
            fit_mode: Optional cover, contain, or auto fitting mode. When set,
                this takes precedence over resize.
            background_option: Background style for contained images (blur or color)
            background_color: Background color when background_option is color

        Returns:
            PIL Image object resized to dimensions, or None on error
        """
        logger.debug("Loading image from BytesIO")
        fit_options = self._resolve_fit_options(
            resize, fit_mode, background_option, background_color
        )

        try:
            return self._open_and_finish(data, dimensions, fit_options)
        except Exception as e:
            logger.error(f"Error loading image from BytesIO: {e}")
            return None

    def _open_and_finish(
        self,
        source,
        dimensions,
        fit_options,
        *,
        use_draft=False,
        log_action="Loaded",
    ):
        """Open an image source and send it through the shared finishing pipeline."""
        img = Image.open(source)
        original_size = img.size
        original_pixels = original_size[0] * original_size[1]
        logger.info(f"{log_action} image: {original_size[0]}x{original_size[1]} ({img.mode} mode, {original_pixels/1_000_000:.1f}MP)")

        if use_draft and fit_options is not None:
            img.draft('RGB', (dimensions[0] * 2, dimensions[1] * 2))
            logger.debug("Draft mode applied - PIL will decode at reduced resolution")
            img.load()
            logger.debug(f"Image decoded: {img.size[0]}x{img.size[1]} (draft mode reduced from {original_size[0]}x{original_size[1]})")

        if fit_options is None:
            return self._apply_orientation(img, original_size)

        return self._process_and_fit(img, dimensions, original_size, *fit_options)

    def _load_from_file(self, path, dimensions, fit_options, use_draft=False):
        """Load and process a local image with optional low-memory decoding."""
        try:
            return self._open_and_finish(
                path,
                dimensions,
                fit_options,
                use_draft=use_draft,
            )
        except MemoryError as e:
            if use_draft:
                logger.error(f"Out of memory while loading {path}: {e}")
                logger.error("Try using a smaller image or enabling more swap space")
                gc.collect()
            else:
                logger.error(f"Error loading image from {path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading image from {path}: {e}")
            return None

    def _load_from_url(
        self,
        url,
        dimensions,
        timeout_ms,
        headers,
        fit_options,
        use_temp_file=False,
    ):
        """Download and process an image using the selected resource strategy."""
        tmp_path = None

        try:
            request_headers = {**self.DEFAULT_HEADERS, **(headers or {})}
            session = get_http_session()
            response = session.get(
                url,
                timeout=timeout_ms / 1000,
                stream=True,
                headers=request_headers,
            )
            response.raise_for_status()

            if not use_temp_file:
                logger.debug("Using in-memory processing (high-performance mode)")
                return self._open_and_finish(
                    BytesIO(response.content),
                    dimensions,
                    fit_options,
                    log_action="Downloaded",
                )

            logger.debug("Using disk-based streaming (low-resource mode)")
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                tmp_path = tmp.name
                downloaded_bytes = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp.write(chunk)
                        downloaded_bytes += len(chunk)

                logger.debug(f"Downloaded {downloaded_bytes / 1024:.1f}KB to temp file")

            return self._load_from_file(
                tmp_path, dimensions, fit_options, use_draft=True
            )

        except Exception as e:
            logger.error(f"Error processing image from {url}: {e}")
            return None
        finally:
            # Clean up temp file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                    logger.debug(f"Cleaned up temp file: {tmp_path}")
                except Exception as e:
                    logger.warning(f"Could not delete temp file {tmp_path}: {e}")

    # ========== SHARED PROCESSING LOGIC ==========

    def _resolve_fit_options(
        self, resize, fit_mode, background_option, background_color
    ):
        """Map the legacy resize flag and explicit fit mode to one pipeline."""
        if fit_mode is None:
            if not resize:
                return None
            fit_mode = "cover"

        return fit_mode, background_option, background_color

    def _apply_orientation(self, img, original_size):
        """Apply EXIF orientation without otherwise modifying the image."""
        img = ImageOps.exif_transpose(img)
        if img.size != original_size:
            logger.debug(f"EXIF orientation applied: {original_size[0]}x{original_size[1]} -> {img.size[0]}x{img.size[1]}")

        return img

    def _prepare_image(self, img, original_size):
        """Apply shared orientation and color-mode preparation."""
        img = self._apply_orientation(img, original_size)

        # Convert to RGB if necessary (removes alpha channel, saves memory)
        # E-ink displays don't need alpha channel anyway
        if img.mode in ('RGBA', 'LA', 'P'):
            logger.debug(f"Converting image from {img.mode} to RGB")
            img = img.convert('RGB')

        return img

    def _process_and_fit(
        self,
        img,
        dimensions,
        original_size,
        fit_mode,
        background_option,
        background_color,
    ):
        """Apply cover, contain, or orientation-aware automatic fitting."""
        dimensions = tuple(map(int, dimensions))
        img = self._prepare_image(img, original_size)

        if fit_mode not in IMAGE_FIT_MODES:
            fit_mode = "cover"

        if fit_mode == "auto":
            image_is_landscape = img.width >= img.height
            display_is_landscape = dimensions[0] >= dimensions[1]
            fit_mode = "cover" if image_is_landscape == display_is_landscape else "contain"

        logger.debug(f"Applying {fit_mode} image fitting")
        if fit_mode == "cover":
            if self.is_low_resource:
                img = self._resize_low_resource(img, dimensions)
            else:
                img = self._resize_high_performance(img, dimensions)
        elif background_option == "blur":
            img = pad_image_blur(img, dimensions)
        else:
            color = ImageColor.getcolor(background_color or "white", img.mode)
            img = ImageOps.pad(
                img,
                dimensions,
                method=Image.Resampling.LANCZOS,
                color=color,
            )

        logger.info(f"Image processing complete: {dimensions[0]}x{dimensions[1]}")
        return img

    def _resize_low_resource(self, img, dimensions):
        """Memory-efficient resize for low-resource devices."""
        logger.debug("Using memory-efficient processing (BICUBIC filter)")

        # For very large images, use two-stage resize
        if img.size[0] > dimensions[0] * 2 or img.size[1] > dimensions[1] * 2:
            logger.debug(f"Image is {img.size[0]}x{img.size[1]}, using two-stage resize")

            # Stage 1: Aggressive downsample using thumbnail (in-place, very memory efficient)
            aspect = img.size[0] / img.size[1]
            if aspect > 1:  # Landscape
                intermediate_size = (dimensions[0] * 2, int(dimensions[0] * 2 / aspect))
            else:  # Portrait
                intermediate_size = (int(dimensions[1] * 2 * aspect), dimensions[1] * 2)

            logger.debug(f"Stage 1: Downsampling to ~{intermediate_size[0]}x{intermediate_size[1]} using NEAREST")
            img.thumbnail(intermediate_size, Image.NEAREST)
            logger.debug(f"Stage 1 complete: {img.size[0]}x{img.size[1]}")
            gc.collect()

            # Stage 2: High-quality resize to exact dimensions
            logger.debug(f"Stage 2: Final resize to {dimensions[0]}x{dimensions[1]} using LANCZOS")
            img = ImageOps.fit(img, dimensions, method=Image.LANCZOS)
            logger.debug(f"Stage 2 complete: {dimensions[0]}x{dimensions[1]}")
        else:
            # Direct resize with BICUBIC (fast, sufficient quality for e-ink)
            logger.debug(f"Resizing directly from {img.size[0]}x{img.size[1]} to {dimensions[0]}x{dimensions[1]}")
            img = ImageOps.fit(img, dimensions, method=Image.BICUBIC)

        # Explicit garbage collection
        gc.collect()
        logger.debug("Garbage collection completed")

        return img

    def _resize_high_performance(self, img, dimensions):
        """High-quality resize for powerful devices."""
        logger.debug("Using high-quality processing (LANCZOS filter)")
        logger.debug(f"Resizing from {img.size[0]}x{img.size[1]} to {dimensions[0]}x{dimensions[1]}")

        return ImageOps.fit(img, dimensions, method=Image.LANCZOS)
