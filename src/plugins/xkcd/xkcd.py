"""
XKCD Comic Plugin

This plugin fetches random XKCD comics and formats them for display
on e-ink devices.
"""

import logging
import random
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple, Union

import requests
from PIL import Image

from plugins.base_plugin.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


class XKCD(BasePlugin):
    """
    Plugin for retrieving and displaying XKCD comics.

    This plugin fetches random XKCD comics from xkcd.com, filters for ones
    with suitable dimensions for display, and formats them for e-ink screens.
    """

    def __init__(self, config, **dependencies):
        """
        Initialize the XKCD plugin.

        Args:
            config: Configuration dictionary for the plugin
            **dependencies: Additional dependencies
        """
        self.config = config
        self.latest_comic = self._get_latest_comic_num()
        self.temp_dir = Path(tempfile.gettempdir())

    def generate_image(self, settings, device_config) -> Image.Image:
        """
        Generate a formatted XKCD comic image for display.

        Args:
            settings: Plugin settings
            device_config: Device configuration

        Returns:
            PIL Image object of the processed comic

        Raises:
            RuntimeError: If comic retrieval or processing fails
        """
        try:
            image_path, title = self._get_random_comic()
            if not image_path:
                raise RuntimeError("Failed to get a suitable comic.")

            processed_image_path = self._process_image(image_path, title=title)
            if not processed_image_path:
                raise RuntimeError("Failed to process comic image.")

            return Image.open(processed_image_path)
        except Exception as e:
            logger.error(f"Error generating XKCD image: {e}")
            raise RuntimeError(f"Error generating XKCD image: {e}")

    def _get_latest_comic_num(self) -> int:
        """
        Get the number of the latest XKCD comic.

        Returns:
            int: The number of the latest comic or a fallback value
        """
        try:
            response = requests.get("https://xkcd.com/info.0.json", timeout=10)
            response.raise_for_status()
            return response.json()["num"]
        except Exception as e:
            logger.error(f"Error getting latest comic number: {e}")
            return 3000  # fallback to a reasonable number

    def _get_comic_info(self, num: int) -> Optional[dict]:
        """
        Get the metadata for a specific comic number.

        Args:
            num: Comic number to retrieve

        Returns:
            dict: Comic metadata or None if retrieval failed
        """
        try:
            response = requests.get(f"https://xkcd.com/{num}/info.0.json", timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting comic {num} info: {e}")
            return None

    def _download_image(self, url: str, output_path: Path) -> bool:
        """
        Download an image from URL to the specified path.

        Args:
            url: Image URL to download
            output_path: Path to save the image to

        Returns:
            bool: True if download was successful, False otherwise
        """
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(response.content)
            return True
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return False

    def _is_suitable(self, image_path: Path) -> bool:
        """
        Check if image is suitable for display on the device.

        Checks dimensions and aspect ratio to ensure the comic
        will display well on e-ink screens.

        Args:
            image_path: Path to the image file

        Returns:
            bool: True if the image is suitable, False otherwise
        """
        try:
            with Image.open(image_path) as img:
                return (
                    img.width > (img.height * 1.2)  # Is horizontal
                    and 250 < img.width < 1000
                    and 250 < img.height < 600
                )
        except Exception as e:
            logger.error(f"Error checking image suitability: {e}")
            return False

    def _get_random_comic(self, max_attempts=10) -> Optional[Tuple[Path, str]]:
        """
        Get a random horizontal XKCD comic and its title.

        Tries multiple comics to find one with suitable dimensions.

        Args:
            max_attempts: Maximum number of comics to try

        Returns:
            Tuple of (image path, title) or None if no suitable comic found
        """
        attempts = 0
        while attempts < max_attempts:
            attempts += 1

            # Generate random number between 1 and latest comic
            num = random.randint(1, self.latest_comic)
            logger.info(f"Trying comic #{num} (attempt {attempts}/{max_attempts})")

            # Get comic info
            comic_info = self._get_comic_info(num)
            if not comic_info:
                continue

            # Download image
            image_url = comic_info["img"]
            temp_image_path = self.temp_dir / f"xkcd_{num}.png"

            if not self._download_image(image_url, temp_image_path):
                continue

            if self._is_suitable(temp_image_path):
                logger.info(f"Found suitable comic: #{num} - {comic_info['title']}")
                return temp_image_path, comic_info["safe_title"]
            else:
                logger.info(f"Comic #{num} is not suitable, trying another...")
                if temp_image_path.exists():
                    temp_image_path.unlink()  # Clean up

            # Be nice to the XKCD server
            time.sleep(1)

        logger.error("Failed to find suitable comic after maximum attempts")
        return None

    def _process_image(
        self,
        image_path: Path,
        title: Optional[str] = None,
        padding: int = 10,
        bg_color: str = "white",
    ) -> Optional[Path]:
        """
        Process a comic image for optimal display.

        Scales, crops, and adds padding to the image to fit the display
        dimensions. Optionally adds the comic title to the top center.

        Args:
            image_path: Path to the source image
            title: Optional title to add to the image
            padding: Padding around the image in pixels
            bg_color: Background color for padding

        Returns:
            Path to the processed image or None if processing failed
        """
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            output_path = Path(tmp_file.name)

        # Target dimensions
        target_width = 800
        target_height = 480
        inner_width = target_width - (padding * 2)
        inner_height = target_height - (padding * 2)

        # First, remove alpha channel and scale down if necessary (but never up)
        filter_chain = [
            "format=rgb24",  # Convert to RGB (remove alpha)
        ]

        # Add scaling only if image is larger than inner dimensions
        filter_chain.append(
            f"scale='min({inner_width},iw)':'min({inner_height},ih)':force_original_aspect_ratio=decrease"
        )

        # Center the image and add padding
        filter_chain.extend(
            [
                f"pad={inner_width}:{inner_height}:(ow-iw)/2:(oh-ih)/2:color={bg_color}",
                f"pad={target_width}:{target_height}:{padding}:{padding}:color={bg_color}",
            ]
        )

        # Add title to top center if provided
        if title:
            # Sanitize title for FFmpeg (escape single quotes)
            safe_title = title.replace("'", "\\'")
            # Position for title text
            title_y_position = padding + 20
            # Add text overlay
            filter_chain.append(
                f"drawtext=text='{safe_title}':fontcolor=black:fontsize=20:"
                f"x=(w-text_w)/2:y={title_y_position}"
            )

        cmd = [
            "ffmpeg",
            "-i",
            str(image_path),
            "-vf",
            ",".join(filter_chain),
            "-y",
            str(output_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                return None
            return output_path
        except Exception as e:
            logger.error(f"Error during image processing: {e}")
            return None
