"""
Adaptive Image Loader for InkyPi
Enhanced with Spectra 6 white-point compensation, improved dithering,
highlight preservation, and hardware-accurate palette mapping.
"""

from PIL import Image, ImageOps, ImageEnhance
from io import BytesIO
from utils.http_client import get_http_session
import logging
import gc
import psutil
import requests
import tempfile
import os

logger = logging.getLogger(__name__)


def _is_low_resource_device():
    try:
        total_memory_gb = psutil.virtual_memory().total / (1024 ** 3)
        is_low_resource = total_memory_gb < 1.0
        logger.debug(f"Device RAM: {total_memory_gb:.2f}GB - Low resource mode: {is_low_resource}")
        return is_low_resource
    except Exception as e:
        logger.warning(f"Could not detect device memory: {e}. Defaulting to low-resource mode.")
        return True


class AdaptiveImageLoader:
    DEFAULT_HEADERS = {
        'User-Agent': 'InkyPi/1.0 (https://github.com/fatihak/InkyPi/) Python-requests'
    }

    def __init__(self):
        self.is_low_resource = _is_low_resource_device()

        # Hardware-specific calibrations
        self.display_profiles = {
            (1600, 1200): {
                "saturation": 1.05,
                "contrast": 1.1,
                "brightness": 1.0,
                "sharpness": 1.0,
                "gamma": 1.15
            },
            (800, 480): {
                "saturation": 1.0,
                "contrast": 1.1,
                "brightness": 1.0,
                "sharpness": 1.0,
                "gamma": 1.15
            }
        }

    # ============================================================
    # Public API
    # ============================================================

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
            original_pixels = original_size[0] * original_size[1]
            logger.info(f"Loaded image: {original_size[0]}x{original_size[1]} ({img.mode} mode, {original_pixels/1_000_000:.1f}MP)")

            if resize:
                img = self._process_and_resize(img, dimensions, original_size)
            else:
                img = ImageOps.exif_transpose(img)

            return img
        except Exception as e:
            logger.error(f"Error loading image from BytesIO: {e}")
            return None

    # ============================================================
    # Low-resource implementations
    # ============================================================

    def _load_from_url_lowmem(self, url, dimensions, timeout_ms, resize, headers=None):
        tmp_path = None
        try:
            logger.debug("Using disk-based streaming (low-resource mode)")
            request_headers = {**self.DEFAULT_HEADERS, **(headers or {})}

            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                tmp_path = tmp.name
                session = get_http_session()
                with session.get(url, timeout=timeout_ms / 1000, stream=True, headers=request_headers) as response:
                    response.raise_for_status()

                    downloaded_bytes = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            tmp.write(chunk)
                            downloaded_bytes += len(chunk)

                logger.debug(f"Downloaded {downloaded_bytes / 1024:.1f}KB to temp file")

            return self._load_from_file_lowmem(tmp_path, dimensions, resize)

        except Exception as e:
            logger.error(f"Error downloading image from {url}: {e}")
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                    logger.debug(f"Cleaned up temp file: {tmp_path}")
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

        except MemoryError:
            logger.error(f"Out of memory while loading {path}")
            gc.collect()
            return None
        except Exception as e:
            logger.error(f"Error loading image from {path}: {e}")
            return None

    # ============================================================
    # High-performance implementations
    # ============================================================

    def _load_from_url_fast(self, url, dimensions, timeout_ms, resize, headers=None):
        try:
            request_headers = {**self.DEFAULT_HEADERS, **(headers or {})}

            session = get_http_session()
            with session.get(url, timeout=timeout_ms / 1000, stream=True, headers=request_headers) as response:
                response.raise_for_status()

                response.raw.decode_content = True
                img = Image.open(response.raw)
                img.load()

            original_size = img.size

            if resize:
                img = self._process_and_resize(img, dimensions, original_size)
            else:
                img = ImageOps.exif_transpose(img)

            return img

        except Exception as e:
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

    # ============================================================
    # Spectra-6 enhancements
    # ============================================================

    def _apply_unified_tonecurve(self, img, gamma):
        """Applies Gamma, White-Point, and Highlight Clipping in a single RAM-efficient pass."""
        lut = []
        # Multipliers for R, G, B (Cool White compensation)
        for channel_mult in (0.98, 1.00, 1.06): 
            for i in range(256):
                # 1. Apply Gamma
                val = 255 * (i / 255.0) ** (1.0 / gamma) if i > 0 else 0
                # 2. Apply White Point Shift
                val = val * channel_mult
                # 3. Preserve Highlights (Force to pure white paper for values > 240)
                val = 255 if val > 240 else val
                # 4. Clamp to 0-255 bounds
                lut.append(max(0, min(255, int(val))))
        
        return img.point(lut)

    def _spectra6_palette(self):
        # Hardware palette MUST remain pure to prevent dither stippling in white areas
        palette_data = [
            0, 0, 0,         # Black
            255, 255, 255,   # Pure White
            255, 0, 0,       # Red
            255, 255, 0,     # Yellow
            0, 255, 0,       # Green
            0, 0, 255        # Blue
        ]
        palette_data += [0] * (768 - len(palette_data))
        palette_img = Image.new('P', (1, 1))
        palette_img.putpalette(palette_data)
        return palette_img

    def _apply_spectra6_dither(self, img):
        palette_img = self._spectra6_palette()
        return img.quantize(palette=palette_img, dither=Image.FLOYDSTEINBERG).convert('RGB')

    # ============================================================
    # Shared processing logic
    # ============================================================

    def _process_and_resize(self, img, dimensions, original_size):
        img = ImageOps.exif_transpose(img)

        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')

        if self.is_low_resource:
            img = self._resize_low_resource(img, dimensions)
        else:
            img = self._resize_high_performance(img, dimensions)

        # Apply Gamma, White-Point, and Highlights efficiently via unified LUT
        gamma = self.display_profiles.get(dimensions, {}).get("gamma", 1.15)
        img = self._apply_unified_tonecurve(img, gamma)

        # Saturation / contrast / brightness / sharpness
        profile = self.display_profiles.get(dimensions, {
            "saturation": 1.0,
            "contrast": 1.0,
            "brightness": 1.0,
            "sharpness": 1.0
        })

        if profile["saturation"] != 1.0:
            img = ImageEnhance.Color(img).enhance(profile["saturation"])
        if profile["contrast"] != 1.0:
            img = ImageEnhance.Contrast(img).enhance(profile["contrast"])
        if profile["brightness"] != 1.0:
            img = ImageEnhance.Brightness(img).enhance(profile["brightness"])
        if profile["sharpness"] != 1.0:
            img = ImageEnhance.Sharpness(img).enhance(profile["sharpness"])

        # Final Spectra-6 dithering
        img = self._apply_spectra6_dither(img)

        logger.info(f"Image processing complete: {dimensions} with Spectra-6 enhancements")
        return img

    # ============================================================
    # Resize helpers
    # ============================================================

    def _resize_low_resource(self, img, dimensions):
        if img.size[0] > dimensions[0] * 2 or img.size[1] > dimensions[1] * 2:
            aspect = img.size[0] / img.size[1]
            if aspect > 1:
                intermediate_size = (dimensions[0] * 2, int(dimensions[0] * 2 / aspect))
            else:
                intermediate_size = (int(dimensions[1] * 2 * aspect), dimensions[1] * 2)

            img.thumbnail(intermediate_size, Image.NEAREST)
            gc.collect()

        img = ImageOps.fit(img, dimensions, method=Image.LANCZOS)
        gc.collect()
        return img

    def _resize_high_performance(self, img, dimensions):
        return ImageOps.fit(img, dimensions, method=Image.LANCZOS)
