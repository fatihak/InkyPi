import requests
from PIL import Image
from io import BytesIO
import logging

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

def resize_image_keep_height(image, target_height, target_width):
    # Calculate the scale factor to resize the image by height
    scale_factor = target_height / image.height
    new_width = int(image.width * scale_factor)

    # Resize the image while maintaining the aspect ratio
    resized_image = image.resize((new_width, target_height), Image.LANCZOS)

    # If the resized width is smaller than the target width, duplicate the image
    if new_width < target_width:
        canvas = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))  # Transparent canvas
        x_offset = 0
        while x_offset < target_width:
            canvas.paste(resized_image, (x_offset, 0), resized_image)
            x_offset += new_width
        resized_image = canvas.crop((0, 0, target_width, target_height))
    
    # If the resized width is larger than the target width, crop it
    elif new_width > target_width:
        left = (new_width - target_width) // 2
        right = left + target_width
        resized_image = resized_image.crop((left, 0, right, target_height))
    
    return resized_image

def draw_frame(image, target_height, target_width):
    # Calculate the scale factor to resize the image by height
    scale_factor = target_height / image.height
    new_width = int(image.width * scale_factor)

    # Resize the image while maintaining the aspect ratio
    resized_image = image.resize((new_width, target_height), Image.LANCZOS)

    # If the resized width is smaller than the target width, duplicate the image
    if new_width < target_width:
        canvas = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))  # Transparent canvas
        x_offset = 0
        while x_offset < target_width:
            canvas.paste(resized_image, (x_offset, 0), resized_image)
            x_offset += new_width
        resized_image = canvas.crop((0, 0, target_width, target_height))
    
    # If the resized width is larger than the target width, crop it
    elif new_width > target_width:
        left = (new_width - target_width) // 2
        right = left + target_width
        resized_image = resized_image.crop((left, 0, right, target_height))
    
    return resized_image