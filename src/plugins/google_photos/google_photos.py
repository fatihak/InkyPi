from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
from io import BytesIO
import requests
import logging
from typing import List, Dict, Optional, Any
import re
import json5
import random

ImageInfo = Dict[str, Any]
logger = logging.getLogger(__name__)

def get_shared_album_html(album_shared_url: str, timeout_ms=40000):
    try:
        response = requests.get(album_shared_url, timeout=timeout_ms / 1000)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error(f"Error grabbing image from {album_shared_url}: {e}")
    return None

def parse_phase_1(input_html: str) -> Optional[str]:
    """
    Extracts the longest JSON-like string.
    """
    re_pattern = r"(?<=AF_initDataCallback\()(?=.*data)(\{[\s\S]*?)(\);<\/script>)"

    longest_match_content = ""
    for match in re.finditer(re_pattern, input_html):
        current_match_content = match.group(1)
        if len(current_match_content) > len(longest_match_content):
            longest_match_content = current_match_content

    return longest_match_content if longest_match_content else None

def parse_phase_2(input_str: str) -> Optional[Any]:
    try:
        return json5.loads(input_str)
    except Exception as e:
        logger.error(f"Error parsing JS object with json5 in parse_phase_2: {e}")
        logger.error(f"Problematic string start: {input_str[:200]}...")
        return None

def is_contain_data(obj: Any) -> bool:
    """Checks if an object is a dictionary and contains a 'data' key."""
    return isinstance(obj, dict) and 'data' in obj

def is_array(obj: Any) -> bool:
    """Checks if an object is a list."""
    return isinstance(obj, list)

def parse_phase_3(input_data: Any) -> Optional[List[ImageInfo]]:
    if not is_contain_data(input_data):
        return None

    d = input_data.get('data')
    if not is_array(d) or not d:
        return None

    # Assuming d[1] is the main array of image entries based on observed Google Photos structure
    arr = d[1]
    if not is_array(arr):
        return None

    parsed_images: List[ImageInfo] = []
    for e in arr:
        # Each 'e' is expected to be an array with at least 6 elements
        if not is_array(e) or len(e) < 6:
            continue

        uid = e[0]
        image_update_date = e[2]
        album_add_date = e[5]

        # Basic type checks for the main elements
        if not isinstance(uid, str) or not isinstance(image_update_date, (int, float)) or not isinstance(
                album_add_date, (int, float)):
            continue

        detail = e[1]  # This is expected to be another nested array for URL, width, height
        if not is_array(detail) or len(detail) < 3:
            continue

        url = detail[0]
        width = detail[1]
        height = detail[2]

        # Basic type checks for image details
        if not isinstance(url, str) or not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
            continue

        # Append the parsed ImageInfo
        parsed_images.append({"uid": uid, "url": url, "width": int(width), "height": int(height),
                              "imageUpdateDate": int(image_update_date), "albumAddDate": int(album_add_date), })

    return parsed_images if parsed_images else None

def fetch_image_urls(album_shared_url: str) -> Optional[List[ImageInfo]]:
    html = get_shared_album_html(album_shared_url)

    if html is None:
        return None

    ph1 = parse_phase_1(html)
    if ph1 is None:
        logger.error("Phase 1 parsing failed: Could not extract data block from HTML.")
        return None

    ph2 = parse_phase_2(ph1)
    if ph2 is None:
        logger.error("Phase 2 parsing failed: Could not parse JSON/JS object data.")
        return None

    result = parse_phase_3(ph2)
    if result is None:
        logger.error("Phase 3 parsing failed: Could not extract image info from parsed data.")
        return None

    return result

def grab_image(image_info, dimensions, timeout_ms=40000):
    """Grab an image from a URL and resize it to the specified dimensions."""
    original_url = image_info['url']

    # Construct the dimensioned URL
    dimension_string = f"=w{dimensions[0]}-h{dimensions[1]}"
    cleaned_url = re.sub(r'=[swh]\d+(-h\d+)?$', '', original_url)
    download_url = f"{cleaned_url}{dimension_string}"
    try:
        response = requests.get(download_url, timeout=timeout_ms / 1000)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))
        return img
    except Exception as e:
        logger.error(f"Error grabbing image from {download_url}: {e}")
        return None

class GooglePhotos(BasePlugin):   
    def generate_image(self, settings, device_config):
        url = settings.get('url')
        if not url:
            raise RuntimeError("URL is required.")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        logger.info(f"Grabbing image from: {url}")

        image_infos = fetch_image_urls(url)
        if image_infos is None:
            raise RuntimeError("Could not fetch image infos from Google Photos album.")

        random_image_info = random.choice(image_infos)
        image = grab_image(random_image_info, dimensions, timeout_ms=40000)

        if not image:
            raise RuntimeError("Failed to load image, please check logs.")

        return image