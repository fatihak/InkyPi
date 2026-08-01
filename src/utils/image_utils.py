"""
Adaptive Image Loader for InkyPi
Centralized image loading and processing with device-aware optimizations.

Automatically uses memory-efficient strategies on low-RAM devices (Pi Zero)
and high-performance strategies on capable devices (Pi 3/4).
Includes Spectra-6 calibration profiles, gamut compression, and memory guardrails.
Assumes strict landscape orientation.
"""

from PIL import Image, ImageOps, ImageEnhance, ImageStat
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
    """Detect if running on a low-resource device (e.g., Raspberry Pi Zero)."""
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

    # Spectra 6 Palette definition (6 physical pigments)
    SPECTRA_6_PALETTE = [
        0, 0, 0,        # Black
        255, 255, 255,  # White
        255, 0, 0,      # Red
        0, 255, 0,      # Green
        0, 0, 255,      # Blue
        255, 255, 0,    # Yellow
    ]

    def __init__(self):
        self.is_low_resource = _is_low_resource_device()
        
        # Hardware-specific calibrations (Landscape Only)
        self.display_profiles = {
            (1600, 1200): { # 13.3" Spectra 6
                "photo": {"saturation": 1.5, "contrast": 1.2, "brightness": 1.05, "sharpness": 1.2},
                "dashboard": {"saturation": 1.0, "contrast": 1.8, "brightness": 1.05, "sharpness": 1.5}
            },
            (800, 480): {   # 7.3" Spectra 6
                "photo": {"saturation": 1.1, "contrast": 1.05, "brightness": 1.0, "sharpness": 1.2},
                "dashboard": {"saturation": 1.0, "contrast": 1.6, "brightness": 1.0, "sharpness": 1.4}
            }
        }

        # Build master palette image for quantization
        palette_data = self.SPECTRA_6_PALETTE + [0] * (768 - len(self.SPECTRA_6_PALETTE))
        self._palette_img = Image.new("P", (1, 1))
        self._palette_img.putpalette(palette_data)

    def _memory_ok(self, min_free_mb=100):
        """Unified guardrail to check available RAM at runtime."""
        try:
            return psutil.virtual_memory().available > (min_free_mb * 1024 * 1024)
        except Exception:
            return True # If psutil fails, assume memory is fine

    def _get_profile(self, dimensions, content_type="photo"):
        """Fetches the exact profile based on dimensions and content type."""
        display_dict = self.display_profiles.get(dimensions, {})
        
        default_profile = {
            "photo": {"saturation": 1.2, "contrast": 1.1, "brightness": 1.0, "sharpness": 1.2},
            "dashboard": {"saturation": 1.0, "contrast": 1.6, "brightness": 1.0, "sharpness": 1.4}
        }
        
        profile_type = content_type if content_type in ("photo", "dashboard") else "photo"
        return display_dict.get(profile_type, default_profile[profile_type])

    def _detect_content_type(self, img):
        """
        Ultra-fast content detection using ImageStat Entropy.
        Photos (high detail/noise) have high entropy.
        Dashboards (flat UI/text) have low entropy.
        """
        # Create a tiny working copy for speed
        test_img = img.copy()
        test_img.thumbnail((300, 300), Image.NEAREST)
        
        # Grayscale entropy calculation is fastest
        stat = ImageStat.Stat(test_img.convert("L"))
        entropy = stat.entropy[0]
        
        # 4.5 is a standard threshold; adjust slightly if needed for your specific dashboard styles
        if entropy > 4.5:
            logger.debug(f"Entropy {entropy:.2f} > 4.5. Content type: photo")
            return "photo"
        else:
            logger.debug(f"Entropy {entropy:.2f} <= 4.5. Content type: dashboard")
            return "dashboard"

    def _apply_gamut_compression(self, img):
        """
        Aligns raw RGB values closer to Spectra-6 physical pigments using a fast C-level affine matrix.
        - Blues shift darker (to hit the Navy pigment instead of White).
        - Greens shift darker (to hit Forest Green).
        - Reds stay vibrant.
        """
        # Affine mapping: R_out, G_out, B_out = M * (R_in, G_in, B_in)
        # 12-tuple structure: (Rr, Rg, Rb, R_offset, Gr, Gg, Gb, G_offset, Br, Bg, Bb, B_offset)
        spectra_matrix = (
            1.0, 0.0, 0.0, 0.0,   # R remains untouched
            0.0, 0.95, 0.0, 0.0,  # G slightly darkened
            0.0, 0.0, 0.85, 0.0   # B noticeably darkened
        )
        return img.convert("RGB", spectra_matrix)

    def quantize_for_spectra6(self, img, content_type="photo"):
        """
        Quantizes an RGB image into the native 6-color Spectra palette.
        Use NONE for dashboards (sharp text) and FLOYDSTEINBERG for photos.
        """
        if img.mode != "RGB":
            img = img.convert("RGB")
            
        dither_method = Image.Dither.NONE if content_type == "dashboard" else Image.Dither.FLOYDSTEINBERG
        return img.quantize(palette=self._palette_img, dither=dither_method)

    def from_url(self, url, dimensions, timeout_ms=40000, resize=True, headers=None, content_type="auto", fit_mode="cover"):
        logger.debug(f"Loading image from URL: {url} ({content_type} mode)")
        if self.is_low_resource:
            return self._load_from_url_lowmem(url, dimensions, timeout_ms, resize, headers, content_type, fit_mode)
        else:
            return self._load_from_url_fast(url, dimensions, timeout_ms, resize, headers, content_type, fit_mode)

    def from_file(self, path, dimensions, resize=True, content_type="auto", fit_mode="cover"):
        logger.debug(f"Loading image from file: {path} ({content_type} mode)")
        if not os.path.exists(path):
            logger.error(f"File not found: {path}")
            return None

        try:
            if self.is_low_resource:
                return self._load_from_file_lowmem(path, dimensions, resize, content_type, fit_mode)
            else:
                return self._load_from_file_fast(path, dimensions, resize, content_type, fit_mode)
        except Exception as e:
            logger.error(f"Error loading image from {path}: {e}")
            return None

    def from_bytesio(self, data, dimensions, resize=True, content_type="auto", fit_mode="cover"):
        try:
            img = Image.open(data)
            original_size = img.size

            if content_type == "auto":
                content_type = self._detect_content_type(img)

            if resize:
                img = self._process_and_resize(img, dimensions, original_size, content_type, fit_mode)
            else:
                img = ImageOps.exif_transpose(img)

            return img
        except Exception as e:
            logger.error(f"Error loading image from BytesIO: {e}")
            return None

    # ========== LOW-RESOURCE IMPLEMENTATIONS ==========

    def _load_from_url_lowmem(self, url, dimensions, timeout_ms, resize, headers=None, content_type="auto", fit_mode="cover"):
        tmp_path = None
        try:
            request_headers = {**self.DEFAULT_HEADERS, **(headers or {})}
            temp_dir = "/var/tmp" if os.path.exists("/var/tmp") else None

            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg', dir=temp_dir) as tmp:
                tmp_path = tmp.name
                session = get_http_session()
                response = session.get(url, timeout=timeout_ms / 1000, stream=True, headers=request_headers)
                response.raise_for_status()

                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp.write(chunk)

            return self._load_from_file_lowmem(tmp_path, dimensions, resize, content_type, fit_mode)

        except Exception as e:
            logger.error(f"Error processing URL image {url}: {e}")
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception as e:
                    logger.warning(f"Could not delete temp file {tmp_path}: {e}")

    def _load_from_file_lowmem(self, path, dimensions, resize, content_type="auto", fit_mode="cover"):
        try:
            img = Image.open(path)
            original_size = img.size

            if content_type == "auto":
                content_type = self._detect_content_type(img)

            if resize:
                # Trigger libjpeg scale-on-load to heavily reduce RAM usage on JPEGs
                if getattr(img, "format", None) in ("JPEG", "MPO"):
                    try:
                        img.draft('RGB', (dimensions[0] * 2, dimensions[1] * 2))
                    except Exception as e:
                        logger.debug(f"Draft mode failed or unsupported: {e}")

                img.load()
                img = self._process_and_resize(img, dimensions, original_size, content_type, fit_mode)
            else:
                img = ImageOps.exif_transpose(img)

            return img

        except MemoryError as e:
            logger.error(f"Out of memory loading {path}: {e}")
            gc.collect()
            return None
        except Exception as e:
            logger.error(f"Error loading file {path}: {e}")
            return None

    # ========== HIGH-PERFORMANCE IMPLEMENTATIONS ==========

    def _load_from_url_fast(self, url, dimensions, timeout_ms, resize, headers=None, content_type="auto", fit_mode="cover"):
        try:
            request_headers = {**self.DEFAULT_HEADERS, **(headers or {})}
            session = get_http_session()
            response = session.get(url, timeout=timeout_ms / 1000, stream=True, headers=request_headers)
            response.raise_for_status()

            img = Image.open(BytesIO(response.content))
            original_size = img.size

            if content_type == "auto":
                content_type = self._detect_content_type(img)

            if resize:
                img = self._process_and_resize(img, dimensions, original_size, content_type, fit_mode)
            else:
                img = ImageOps.exif_transpose(img)

            return img
        except Exception as e:
            logger.error(f"Error downloading {url}: {e}")
            return None

    def _load_from_file_fast(self, path, dimensions, resize, content_type="auto", fit_mode="cover"):
        try:
            img = Image.open(path)
            original_size = img.size

            if content_type == "auto":
                content_type = self._detect_content_type(img)

            if resize:
                img = self._process_and_resize(img, dimensions, original_size, content_type, fit_mode)
            else:
                img = ImageOps.exif_transpose(img)

            return img
        except Exception as e:
            logger.error(f"Error loading file {path}: {e}")
            return None

    # ========== SHARED PROCESSING LOGIC ==========

    def _process_and_resize(self, img, dimensions, original_size, content_type="photo", fit_mode="cover"):
        img = ImageOps.exif_transpose(img)

        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
            
        # Spectra-6 Gamut Compression
        if content_type == "photo":
            img = self._apply_gamut_compression(img)

        # Verify memory before intensive operations
        mem_ok = self._memory_ok(100)
        if not mem_ok:
            logger.warning("Low memory detected (<100MB free). Executing fallback processing.")

        # Resize strategy
        if self.is_low_resource:
            img = self._resize_low_resource(img, dimensions, fit_mode, mem_ok)
        else:
            img = self._resize_high_performance(img, dimensions, fit_mode)

        # Apply image enhancements ONLY if memory allows
        if mem_ok:
            profile = self._get_profile(dimensions, content_type)

            if profile.get("saturation", 1.0) != 1.0:
                img = ImageEnhance.Color(img).enhance(profile["saturation"])

            if profile.get("contrast", 1.0) != 1.0:
                img = ImageEnhance.Contrast(img).enhance(profile["contrast"])

            if profile.get("brightness", 1.0) != 1.0:
                img = ImageEnhance.Brightness(img).enhance(profile["brightness"])

            if profile.get("sharpness", 1.0) != 1.0:
                img = ImageEnhance.Sharpness(img).enhance(profile["sharpness"])

        return img

    def _resize_low_resource(self, img, dimensions, fit_mode="cover", mem_ok=True):
        # Fall back to NEAREST if RAM is critically low, otherwise use standard strategy
        filter_method = Image.LANCZOS if (fit_mode == "cover" and mem_ok) else Image.BICUBIC
        if not mem_ok:
            filter_method = Image.NEAREST

        if img.size[0] > dimensions[0] * 2 or img.size[1] > dimensions[1] * 2:
            aspect = img.size[0] / img.size[1]
            if aspect > 1:
                intermediate_size = (dimensions[0] * 2, int(dimensions[0] * 2 / aspect))
            else:
                intermediate_size = (int(dimensions[1] * 2 * aspect), dimensions[1] * 2)

            img.thumbnail(intermediate_size, Image.NEAREST)
            gc.collect()

        if fit_mode == "contain":
            img = ImageOps.pad(img, dimensions, color=(255, 255, 255), method=filter_method)
        else:
            img = ImageOps.fit(img, dimensions, method=filter_method)

        gc.collect()
        return img

    def _resize_high_performance(self, img, dimensions, fit_mode="cover"):
        if fit_mode == "contain":
            return ImageOps.pad(img, dimensions, color=(255, 255, 255), method=Image.LANCZOS)
        return ImageOps.fit(img, dimensions, method=Image.LANCZOS)
