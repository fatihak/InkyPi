import logging
import os
import uuid
from werkzeug.utils import secure_filename
import socket
import subprocess

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

FONT_FAMILIES = {
    "Dogica": [{
        "font-weight": "normal",
        "file": "dogicapixel.ttf"
    },{
        "font-weight": "bold",
        "file": "dogicapixelbold.ttf"
    }],
    "Jost": [{
        "font-weight": "normal",
        "file": "Jost.ttf"
    },{
        "font-weight": "bold",
        "file": "Jost-SemiBold.ttf"
    }],
    "Napoli": [{
        "font-weight": "normal",
        "file": "Napoli.ttf"
    }],
    "DS-Digital": [{
        "font-weight": "normal",
        "file": os.path.join("DS-DIGI", "DS-DIGI.TTF")
    }]
}

FONTS = {
    "ds-gigi": "DS-DIGI.TTF",
    "napoli": "Napoli.ttf",
    "jost": "Jost.ttf",
    "jost-semibold": "Jost-SemiBold.ttf"
}

def resolve_path(file_path):
    src_dir = os.getenv("SRC_DIR")
    if src_dir is None:
        # Default to the src directory
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    src_path = Path(src_dir)
    return str(src_path / file_path)

def get_ip_address():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
    return ip_address

def get_wifi_name():
    try:
        output = subprocess.check_output(['iwgetid', '-r']).decode('utf-8').strip()
        return output
    except subprocess.CalledProcessError:
        return None

def is_connected():
    """Check if the Raspberry Pi has an internet connection."""
    try:
        # Try to connect to Google's public DNS server
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False

def get_font(font_name, font_size=50, font_weight="normal"):
    if font_name in FONT_FAMILIES:
        font_variants = FONT_FAMILIES[font_name]

        font_entry = next((entry for entry in font_variants if entry["font-weight"] == font_weight), None)
        if font_entry is None:
            font_entry = font_variants[0]  # Default to first available variant

        if font_entry:
            font_path = resolve_path(os.path.join("static", "fonts", font_entry["file"]))
            return ImageFont.truetype(font_path, font_size)
        else:
            logger.warning(f"Requested font weight not found: font_name={font_name}, font_weight={font_weight}")
    else:
        logger.warning(f"Requested font not found: font_name={font_name}")

    return None

def get_fonts():
    fonts_list = []
    for font_family, variants in FONT_FAMILIES.items():
        for variant in variants:
            fonts_list.append({
                "font_family": font_family,
                "url": resolve_path(os.path.join("static", "fonts", variant["file"])),
                "font_weight": variant.get("font-weight", "normal"),
                "font_style": variant.get("font-style", "normal"),
            })
    return fonts_list

def get_font_path(font_name):
    return resolve_path(os.path.join("static", "fonts", FONTS[font_name]))

def generate_startup_image(dimensions=(800,480)):
    bg_color = (255,255,255)
    text_color = (0,0,0)
    width, height = dimensions

    hostname = socket.gethostname()
    ip = get_ip_address()

    image = Image.new("RGBA", dimensions, bg_color)
    image_draw = ImageDraw.Draw(image)

    title_font_size = width * 0.145
    image_draw.text((width/2, height/2), "inkypi", anchor="mm", fill=text_color, font=get_font("Jost", title_font_size))

    text = f"To get started, visit http://{hostname}.local"
    text_font_size = width * 0.032

    # Draw the instructions
    y_text = height * 3 / 4
    image_draw.text((width/2, y_text), text, anchor="mm", fill=text_color, font=get_font("Jost", text_font_size))

    # Draw the IP on a line below
    ip_text = f"or http://{ip}"
    ip_text_font_size = width * 0.032
    bbox = image_draw.textbbox((0, 0), text, font=get_font("Jost", text_font_size))
    text_height = bbox[3] - bbox[1]
    ip_y = y_text + text_height * 1.35
    image_draw.text((width/2, ip_y), ip_text, anchor="mm", fill=text_color, font=get_font("Jost", ip_text_font_size))

    return image

def is_cross_origin_request(origin, sec_fetch_site, host):
    """True when a browser tells us the request was initiated by a page from another origin."""
    if sec_fetch_site and sec_fetch_site not in ("same-origin", "none"):
        return True
    if origin:
        if origin == "null":
            return True
        from urllib.parse import urlsplit
        return urlsplit(origin).netloc.lower() != (host or "").lower()
    return False  # non-browser clients (curl, scripts) send neither header

def parse_form(request_form):
    request_dict = request_form.to_dict()
    for key in request_form.keys():
        if key.endswith('[]'):
            request_dict[key] = request_form.getlist(key)
    return request_dict

ALLOWED_UPLOAD_EXTENSIONS = {'png', 'avif', 'jpg', 'jpeg', 'gif', 'webp', 'heif', 'heic'}

def get_upload_dir():
    return resolve_path(os.path.join("static", "images", "saved"))

def is_upload_path(path):
    """True only for files inside the upload directory (rejects traversal and arbitrary paths)."""
    if not isinstance(path, str) or not path:
        return False
    upload_dir = os.path.realpath(get_upload_dir())
    return os.path.realpath(path).startswith(upload_dir + os.sep)

def filter_upload_paths(paths):
    """Keeps only paths that point inside the upload directory, logging anything else."""
    if isinstance(paths, str):
        paths = [paths]
    safe = []
    for path in paths or []:
        if is_upload_path(path):
            safe.append(path)
        else:
            logger.warning(f"Ignoring file path outside of upload directory: {path!r}")
    return safe

def delete_upload_files(paths):
    for path in filter_upload_paths(paths):
        if os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"Deleted uploaded image: {path}")
            except OSError as e:
                logger.warning(f"Failed to delete uploaded image {path}: {e}")

def handle_request_files(request_files, form_data={}):
    file_location_map = {}
    # handle existing file locations being provided as part of the form data
    for key in set(request_files.keys()):
        is_list = key.endswith('[]')
        if key in form_data:
            existing = filter_upload_paths(form_data.getlist(key) if is_list else [form_data.get(key)])
            file_location_map[key] = existing if is_list else (existing[0] if existing else None)
    # add new files in the request
    for key, file in request_files.items(multi=True):
        is_list = key.endswith('[]')
        file_name = file.filename
        if not file_name:
            continue

        extension = os.path.splitext(file_name)[1].replace('.', '').lower()
        if not extension or extension not in ALLOWED_UPLOAD_EXTENSIONS:
            continue

        # Unique prefix: identical names from different instances must not overwrite each other
        file_name = f"{uuid.uuid4().hex[:8]}_{secure_filename(os.path.basename(file_name)) or 'image.' + extension}"

        file_save_dir = get_upload_dir()
        os.makedirs(file_save_dir, exist_ok=True)
        file_path = os.path.join(file_save_dir, file_name)

        # Open the image and apply EXIF transformation before saving
        if extension in {'jpg', 'jpeg'}:
            try:
                with Image.open(file) as img:
                    img = ImageOps.exif_transpose(img)
                    img.save(file_path, quality=95)
            except Exception as e:
                logger.warning(f"EXIF processing error for {file_name}: {e}")
                file.stream.seek(0)  # the failed decode consumed part of the stream
                file.save(file_path)
        else:
            # Directly save non-JPEG files
            file.save(file_path)

        if is_list:
            file_location_map.setdefault(key, [])
            file_location_map[key].append(file_path)
        else:
            file_location_map[key] = file_path
    return file_location_map
