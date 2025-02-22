import requests
from PIL import Image
from io import BytesIO
import logging
import hashlib
import imgkit
from pyppeteer import launch
import asyncio


logger = logging.getLogger(__name__)

def get_image(image_url):
    response = requests.get(image_url)
    img = None
    if 200 <= response.status_code < 300 or response.status_code == 304:
        img = Image.open(BytesIO(response.content))
    else:
        logger.error(f"Received non-200 response from {image_url}: status_code: {response.status_code}")
    return img

def change_orientation(image, orientation):
    if orientation == 'horizontal':
        image = image.rotate(0, expand=1)
    elif orientation == 'vertical':
        image = image.rotate(90, expand=1)
    return image

def resize_image(image, desired_size, image_settings=[]):
    img_width, img_height = image.size
    desired_width, desired_height = desired_size
    desired_width, desired_height = int(desired_width), int(desired_height)

    img_ratio = img_width / img_height
    desired_ratio = desired_width / desired_height

    keep_width = "keep-width" in image_settings

    x_offset, y_offset = 0,0
    new_width, new_height = img_width,img_height
    # Step 1: Determine crop dimensions
    desired_ratio = desired_width / desired_height
    if img_ratio > desired_ratio:
        # Image is wider than desired aspect ratio
        new_width = int(img_height * desired_ratio)
        if not keep_width:
            x_offset = (img_width - new_width) // 2
    else:
        # Image is taller than desired aspect ratio
        new_height = int(img_width / desired_ratio)
        if not keep_width:
            y_offset = (img_height - new_height) // 2

    # Step 2: Crop the image
    cropped_image = image.crop((x_offset, y_offset, x_offset + new_width, y_offset + new_height))

    # Step 3: Resize to the exact desired dimensions (if necessary)
    return cropped_image.resize((desired_width, desired_height), Image.LANCZOS)

def compute_image_hash(image):
    """Compute SHA-256 hash of an image."""
    image = image.convert("RGB")
    img_bytes = image.tobytes()
    return hashlib.sha256(img_bytes).hexdigest()

def take_screenshot(dimensions, html, css=[]):
    """Takes a screenshot of the given html and css files"""
    width, height = dimensions
    options = {
        'width': width,
        'height': height,
        'disable-smart-width': '',
        'enable-local-file-access': ''
    }
    image_data = imgkit.from_string(html, False, options=options, css=css)
    image = Image.open(BytesIO(image_data))
    return image

async def take_screenshot_html(dimensions, html_content, css_files=[]):
    width, height = dimensions
    browser = await launch(headless=True)
    page = await browser.newPage()

    # Set the HTML content
    await page.setContent(html_content)
    for css in css_files:
        await page.addStyleTag(
            { "path": css }
        )

    await page.setViewport({
        "width": width,
        "height": height,
        "deviceScaleFactor": 0.5
    })

    await page.waitForSelector('.container')
    
    # Take screenshot and get the binary data
    screenshot_bytes = await page.screenshot({'fullPage': True})
    
    await browser.close()
    
    # Load bytes data into a Pillow Image object
    image = Image.open(BytesIO(screenshot_bytes))
    return image