"""
Adaptive Image Loader for InkyPi
Centralized image loading and processing with device-aware optimizations.

Automatically uses memory-efficient strategies on low-RAM devices (Pi Zero/Pi 2W)
and high-performance strategies on capable devices (Pi 3/4).
Includes hardware-specific calibration profiles for Spectra 6 displays.
"""

from PIL import Image, ImageOps, ImageEnhance
from io import BytesIO
from utils.http_client import get_http_session
import logging
import gc
import psutil
import tempfile
import os
import requests

logger = logging.getLogger(__name__)


def _is_low_resource_device():
    """
    Detect if running on a low-resource device (e.g., Raspberry Pi Zero or 2W).
    Returns True if device has less than 1GB RAM, False otherwise.
    """
    try:
        total_memory_gb = psutil.virtual_memory().total / (1024 ** 3)
        is_low_resource = total_memory_gb < 1.0
        logger.debug(f"Device RAM: {total_memory_gb:.2f}GB - Low resource mode: {is_low_resource}")
        return is_low_resource
    except Exception as e:
        logger.warning(f"Could not detect device memory: {e}. Defaulting to low-resource mode.")
        return True


class AdaptiveImageLoader:
    """
    Centralized image loading with device-adaptive optimizations.
    """

    DEFAULT_HEADERS = {
        'User-Agent': 'InkyPi/1.0 (https://github.com/fatihak/InkyPi/) Python-requests'
    }

    def __init__(self):
        self.is_low_resource = _is_low_resource_device()
        
        # Hardware-specific calibrations to prevent dithering artifacts
        # on Pimoroni Spectra 6 displays. 
        self.display_profiles = {
            (1600, 1200): { # 13.3" Spectra 6
                "saturation": 1.5,
                "contrast": 1.2,
                "brightness": 1.05 
            },
            (800, 480): {   # 7.3" Spectra 6
                "saturation": 1.1,
                "contrast": 1.05,
                "brightness": 1.0
            }
        }

    def from_url(self, url, dimensions, timeout_ms=40000, resize=True, headers=None):
        logger.debug(f"Loading image from URL: {url}")
        if self.is_low_resource:
            return self._load_from_url_lowmem(url, dimensions, timeout_ms, resize, headers)
        else:
            return self._load_from_url_fast(url, dimensions, timeout_ms, resize, headers)

    def from_file(self, path, dimensions, resize=True):
        logger.debug(f"Loading image from file: {path}")
        if not os.path.exists(path):
            logger.error(f"File not found: {path}")
            return None

        try:
            if self.is_low_resource:
                return self._load_from_file_lowmem(path, dimensions, resize)
            else:
                return self._load_from_file_fast(path, dimensions, resize)
        except Exception as e:
            logger.error(f"Error loading image from {path}: {e}")
            return None

    def from_bytesio(self, data, dimensions, resize=True):
        logger.debug("Loading image from BytesIO")
        try:
            img = Image.open(data)
            original_size = img.size
            logger.info(f"Loaded image: {original_size[0]}x{original_size[1]}")

            if resize:
                img = self._process_and_resize(img, dimensions, original_size)
            else:
                img = ImageOps.exif_transpose(img)
            return img
        except Exception as e:
            logger.error(f"Error loading image from BytesIO: {e}")
            return None

    # ========== LOW-RESOURCE IMPLEMENTATIONS ==========

    def _load_from_url_lowmem(self, url, dimensions, timeout_ms, resize, headers=None):
        tmp_path = None
        try:
            logger.debug("Using disk-based streaming (low-resource mode)")
            request_headers = {**self.DEFAULT_HEADERS, **(headers or {})}

            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                tmp_path = tmp.name
                session = get_http_session()
                response = session.get(url, timeout=timeout_ms / 1000, stream=True, headers=request_headers)
                response.raise_for_status()

                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp.write(chunk)

            return self._load_from_file_lowmem(tmp_path, dimensions, resize)

        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading image from {url}: {e}")
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception as e:
                    logger.warning(f"Could not delete temp file {tmp_path}: {e}")

    def _load_from_file_lowmem(self, path, dimensions, resize):
        try:
            img = Image.open(path)
            original_size = img.size

            if resize:
                img.draft('RGB', (dimensions[0] * 2, dimensions[1] * 2))
                img.load()
                img = self._process_and_resize(img, dimensions, original_size)
            else:
                img = ImageOps.exif_transpose(img)

            return img

        except MemoryError as e:
            logger.error(f"Out of memory while loading {path}: {e}")
            gc.collect()
            return None
        except Exception as e:
            logger.error(f"Error loading image from {path}: {e}")
            return None

    # ========== HIGH-PERFORMANCE IMPLEMENTATIONS ==========

    def _load_from_url_fast(self, url, dimensions, timeout_ms, resize, headers=None):
        try:
            logger.debug("Using in-memory processing (high-performance mode)")
            request_headers = {**self.DEFAULT_HEADERS, **(headers or {})}

            session = get_http_session()
            response = session.get(url, timeout=timeout_ms / 1000, stream=True, headers=request_headers)
            response.raise_for_status()

            img = Image.open(BytesIO(response.content))
            original_size = img.size

            if resize:
                img = self._process_and_resize(img, dimensions, original_size)
            else:
                img = ImageOps.exif_transpose(img)

            return img

        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading image from {url}: {e}")
            return None

    def _load_from_file_fast(self, path, dimensions, resize):
        try:
            img = Image.open(path)
            original_size = img.size

            if resize:
                img = self._process_and_resize(img, dimensions, original_size)
            else:
                img = ImageOps.exif_transpose(img)

            return img
        except Exception as e:
            logger.error(f"Error loading image from {path}: {e}")
            return None

    # ========== SHARED PROCESSING LOGIC ==========

    def _process_and_resize(self, img, dimensions, original_size):
        img = ImageOps.exif_transpose(img)
        
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')

        # 1. Resize via memory-efficient or high-perf paths
        if self.is_low_resource:
            img = self._resize_low_resource(img, dimensions)
        else:
            img = self._resize_high_performance(img, dimensions)

        # 2. Fetch specific hardware profile (defaults to 1.0 if size not found)
        profile = self.display_profiles.get(dimensions, {"saturation": 1.0, "contrast": 1.0, "brightness": 1.0})

        # 3. Apply e-ink calibrations
        if profile["saturation"] != 1.0:
            img = ImageEnhance.Color(img).enhance(profile["saturation"])
            
        if profile["contrast"] != 1.0:
            img = ImageEnhance.Contrast(img).enhance(profile["contrast"])
            
        if profile["brightness"] != 1.0:
            img = ImageEnhance.Brightness(img).enhance(profile["brightness"])

        return img

    def _resize_low_resource(self, img, dimensions):
        if img.size[0] > dimensions[0] * 2 or img.size[1] > dimensions[1] * 2:
            aspect = img.size[0] / img.size[1]
            if aspect > 1:
                intermediate_size = (dimensions[0] * 2, int(dimensions[0] * 2 / aspect))
            else:
                intermediate_size = (int(dimensions[1] * 2 * aspect), dimensions[1] * 2)

            img.thumbnail(intermediate_size, Image.BILINEAR)
            gc.collect()

        # Always use LANCZOS for the final fit to preserve edge crispness on e-ink
        img = ImageOps.fit(img, dimensions, method=Image.LANCZOS)
        gc.collect()
        return img

    def _resize_high_performance(self, img, dimensions):
        return ImageOps.fit(img, dimensions, method=Image.LANCZOS)
