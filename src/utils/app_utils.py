import logging
import os
import socket
import subprocess

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

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
    src_path = Path(os.getenv("SRC_DIR"))

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
            logger.warn(f"Requested font weight not found: font_name={font_name}, font_weight={font_weight}")
    else:
        logger.warn(f"Requested font not found: font_name={font_name}")

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

def generate_startup_image(install = False, dimensions=(800,480)):
    bg_color = (255,255,255)
    text_color = (0,0,0)
    width,height = dimensions

    hostname = socket.gethostname()

    image = Image.new("RGBA", dimensions, bg_color)
    image_draw = ImageDraw.Draw(image)

    title_font_size = width * 0.145
    image_draw.text((width/2, height*0.20), "inkypi", anchor="mm", fill=text_color, font=get_font("Jost", title_font_size))

    if install:
        text = f"To get started, connect a device (like your phone)\nwith the display via WIFI: \nSSID: INKY\nPassword: SuperSecret123\n\nand connect to http://10.42.0.1"
    else:
        ip = get_ip_address()
        text = f"Your inkypi is now connected to your wifi, please visit\nhttp://{hostname}.local\nor\nhttp://{ip}\nto configure more."
    text_font_size = width * 0.032
    image_draw.text((width/2, height*0.60), text, anchor="mm", fill=text_color, font=get_font("Jost", text_font_size), align="center")

    return image

def handle_request_files(request_files, form_data={}):
    allowed_file_extensions = {'pdf', 'png', 'jpg', 'jpeg', 'gif'}
    file_location_map = {}
    # handle existing file locations being provided as part of the form data
    for key in set(request_files.keys()):
        is_list = key.endswith('[]')
        if key in form_data:
            file_location_map[key] = form_data.getlist(key) if is_list else form_data.get(key)
    # add new files in the request
    for key, file in request_files.items(multi=True):
        is_list = key.endswith('[]')
        file_name = file.filename
        if not file_name:
            continue

        extension = os.path.splitext(file_name)[1].replace('.', '')
        if not extension or extension.lower() not in allowed_file_extensions:
            continue

        file_name = os.path.basename(file_name)

        file_save_dir = resolve_path(os.path.join("static", "images", "saved"))
        file_path = os.path.join(file_save_dir, file_name)
        file.save(file_path)

        if is_list:
            file_location_map.setdefault(key, [])
            file_location_map[key].append(file_path)
        else:
            file_location_map[key] = file_path
    return file_location_map

def set_hostname(new_hostname):
    # Set hostname
    with open('/etc/hostname', 'w') as f:
        f.write(new_hostname)

    # edit hosts file
    with open('/etc/hosts', 'r') as f:
        lines = f.readlines()

    with open('/etc/hosts', 'w') as f:
        for line in lines:
            if socket.gethostname() in line:
                f.write(line.replace(socket.gethostname(), new_hostname))
            else:
                f.write(line)

    # set hostname with hostnamectl
    os.system(f'hostnamectl set-hostname {new_hostname}')
    logger.info(f"set hostname to {new_hostname}")
