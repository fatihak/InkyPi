from widgets.base_widget.base_widget import BaseWidget
from utils.app_utils import get_font
from PIL import Image, ImageDraw, ImageFont
import logging

class StaticMessage(BaseWidget):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        return template_params

    def generate_image(self, settings, device_config):
        # Generate a small overlay image (e.g., 150x80)
        overlay = Image.new('RGBA', (150, 80), (0, 0, 0, 0))  # Transparent
        draw = ImageDraw.Draw(overlay)

        font_size = int(settings.get('font_size', 18))
        font = get_font("Jost", font_size) or ImageFont.load_default()

        # Use text color from settings, default to black
        use_contrast_color = settings.get('use_contrast_color', False)
        if use_contrast_color:
            text_color = settings.get('contrast_color', "#FFFFFF")
        else:
            text_color = settings.get('text_color', "#FFFFFF")
        static_message = settings.get('static_message', "Hello Widget")

        # Get text size for centering and calculating required space
        bbox = draw.textbbox((0, 0), static_message, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Expand overlay if text is larger than default 150x80
        if text_width > 150 or text_height > 80:
            overlay = Image.new('RGBA', (max(150, text_width), max(80, text_height)), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

        draw.text((0, 0), static_message, fill=text_color, font=font)

        # Crop to actual text size
        bbox = draw.textbbox((0, 0), static_message, font=font)
        return overlay.crop(bbox)
