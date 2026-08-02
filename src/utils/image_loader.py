import io
import os
import math
import logging
import requests
from PIL import Image, ImageEnhance

logger = logging.getLogger(__name__)

def _is_low_resource_device():
    """Detects if running on a low-memory device like Pi Zero."""
    try:
        with open("/proc/meminfo", "r") as f:
            meminfo = f.read()
        for line in meminfo.splitlines():
            if "MemTotal" in line:
                total_kb = int(line.split()[1])
                if total_kb < 600000:  # < 600MB indicates Pi Zero 2 or similar
                    return True
    except Exception:
        pass
    return False

class AdaptiveImageLoader:
    """
    Centralized image loading with device-adaptive optimizations and Spectra 6 tuning.
    """
    DEFAULT_HEADERS = {
        'User-Agent': 'InkyPi/1.0 (https://github.com/fatihak/InkyPi/) Python-requests'
    }

    def __init__(self, device_config=None):
        self.is_low_resource = _is_low_resource_device()
        
        # --- GLOBAL TEST SWITCH ---
        # Pulls from device_config.json, defaults to "auto" if missing
        self.force_mode = "auto"
        if device_config and hasattr(device_config, "get_config"):
            self.force_mode = device_config.get_config("force_image_mode", default="auto")
        
        # Hardware-specific calibrations
        self.display_profiles = {
            "spectra_6": {
                "palette": [
                    0, 0, 0,          # Black
                    255, 255, 255,    # White
                    0, 255, 0,        # Green
                    0, 0, 255,        # Blue
                    255, 0, 0,        # Red
                    255, 255, 0       # Yellow
                ],
                "saturation_boost": 1.2,
                "contrast_boost": 1.1
            }
        }

    def _detect_content_type(self, img):
        """Safe entropy calculation using image histogram."""
        
        # Intercept the calculation if the JSON switch is active
        if self.force_mode in ("photo", "dashboard"):
            logger.info(f"JSON OVERRIDE: Forcing image mode to '{self.force_mode}'")
            return self.force_mode

        try:
            test_img = img.copy()
            test_img.thumbnail((300, 300), Image.NEAREST)
            histogram = test_img.convert("L").histogram()
            total_pixels = sum(histogram)
            
            if total_pixels == 0:
                return "dashboard"
                
            entropy = 0.0
            for count in histogram:
                if count > 0:
                    prob = count / total_pixels
                    entropy -= prob * math.log2(prob)
            
            logger.info(f"Calculated image entropy: {entropy:.2f}")
            if entropy > 4.5:
                return "photo"
            else:
                return "dashboard"
        except Exception as e:
            logger.debug(f"Entropy detection failed, defaulting to photo: {e}")
            return "photo"

    def _get_spectra6_palette_image(self):
        """Creates a palette image mapping precisely to Spectra 6 hardware colors."""
        palette_img = Image.new('P', (1, 1))
        flat_palette = self.display_profiles["spectra_6"]["palette"]
        # Pad the palette out to 256 colors to satisfy PIL requirements
        flat_palette += [0] * (768 - len(flat_palette))
        palette_img.putpalette(flat_palette)
        return palette_img

    def _process_and_resize(self, img, dimensions, original_size, content_type="auto", fit_mode="cover"):
        """Handles low-resource scaling, color enhancement, and Spectra 6 quantization."""
        
        if content_type == "auto":
            content_type = self._detect_content_type(img)
        
        # --- Memory Protection (Pi Zero) ---
        if self.is_low_resource and max(original_size) > 1600:
            logger.info("Low memory device detected. Performing rapid downscale.")
            img.thumbnail((1600, 1600), Image.NEAREST)

        # --- Scaling ---
        if dimensions:
            if fit_mode == "contain":
                img.thumbnail(dimensions, Image.Resampling.LANCZOS)
            else:
                # Basic cover implementation
                aspect_ratio_img = img.width / img.height
                aspect_ratio_dim = dimensions[0] / dimensions[1]
                if aspect_ratio_img > aspect_ratio_dim:
                    new_width = int(dimensions[1] * aspect_ratio_img)
                    img = img.resize((new_width, dimensions[1]), Image.Resampling.LANCZOS)
                    left = (img.width - dimensions[0]) / 2
                    img = img.crop((left, 0, left + dimensions[0], dimensions[1]))
                else:
                    new_height = int(dimensions[0] / aspect_ratio_img)
                    img = img.resize((dimensions[0], new_height), Image.Resampling.LANCZOS)
                    top = (img.height - dimensions[1]) / 2
                    img = img.crop((0, top, dimensions[0], top + dimensions[1]))

        # Ensure RGB before quantization
        if img.mode != "RGB":
            img = img.convert("RGB")

        # --- Color Correction & Quantization (Spectra 6) ---
        profile = self.display_profiles["spectra_6"]
        
        if content_type == "photo":
            # Boost saturation/contrast before mapping
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(profile["saturation_boost"])
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(profile["contrast_boost"])
            
            # Photos get Floyd-Steinberg dithering
            dither_mode = Image.Dither.FLOYDSTEINBERG
        else:
            # Dashboards skip enhancement to keep colors solid and skip dithering
            dither_mode = Image.Dither.NONE

        palette_img = self._get_spectra6_palette_image()
        img = img.quantize(palette=palette_img, dither=dither_mode)
        
        return img

    def from_url(self, url, dimensions=None, content_type="auto"):
        """Downloads and optimizes an image from a URL."""
        response = requests.get(url, headers=self.DEFAULT_HEADERS, timeout=10)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content))
        return self._process_and_resize(img, dimensions, img.size, content_type)

    def from_file(self, file_path, dimensions=None, content_type="auto"):
        """Loads and optimizes a local image."""
        img = Image.open(file_path)
        return self._process_and_resize(img, dimensions, img.size, content_type)

    def from_bytesio(self, bytes_io, dimensions=None, content_type="auto"):
        """Loads and optimizes from an in-memory byte stream."""
        img = Image.open(bytes_io)
        return self._process_and_resize(img, dimensions, img.size, content_type)
