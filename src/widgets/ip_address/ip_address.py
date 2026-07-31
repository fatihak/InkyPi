from widgets.base_widget.base_widget import BaseWidget
from utils.app_utils import get_font, get_ip_address
from PIL import Image, ImageDraw, ImageFont
import logging
import socket


class IPAddressWidget(BaseWidget):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        return template_params

    def generate_image(self, settings, device_config):
        # Default overlay size
        overlay = Image.new('RGBA', (200, 40), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        font_size = int(settings.get('font_size', 18))
        font = get_font("Jost", font_size) or ImageFont.load_default()

        use_contrast_color = settings.get('use_contrast_color', False)
        if use_contrast_color:
            text_color = settings.get('contrast_color', "#FFFFFF")
        else:
            text_color = settings.get('text_color', "#FFFFFF")

        # Get IP address with fallbacks
        try:
            ip_address = get_ip_address()
        except Exception:
            logging.warning("get_ip_address() raised an exception, falling back to hostname")
            ip_address = None

        if not ip_address:
            try:
                ip_address = socket.gethostname()
            except Exception:
                ip_address = "IP unavailable"

        # Format text
        ip_text = str(ip_address)

        # Measure text bbox
        bbox = draw.textbbox((0, 0), ip_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Expand overlay if text is larger than default
        if text_width > 200 or text_height > 40:
            overlay = Image.new('RGBA', (max(200, text_width), max(40, text_height)), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

        draw.text((0, 0), ip_text, fill=text_color, font=font)

        bbox = draw.textbbox((0, 0), ip_text, font=font)
        return overlay.crop(bbox)
