from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageDraw, ImageFont
from utils.image_utils import resize_image
from io import BytesIO
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class TextRender(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = False  # We'll handle custom styling in our own template
        return template_params

    def generate_image(self, settings, device_config):
        title = settings.get("title", "")
        text_content = settings.get("text_content", "")
        
        if not text_content.strip():
            raise RuntimeError("Text content is required.")
        
        # Limit text to 200 characters
        if len(text_content) > 200:
            text_content = text_content[:200]

        # Get styling options
        font_family = settings.get("font_family", "Jost")
        font_size = settings.get("font_size", "medium")
        text_color = settings.get("text_color", "#000000")
        background_color = settings.get("background_color", "#FFFFFF")
        text_align = settings.get("text_align", "center")
        
        # Debug logging
        logger.info(f"Text Render settings: font={font_family}, size={font_size}, color={text_color}, bg={background_color}, align={text_align}")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        image_template_params = {
            "title": title,
            "content": text_content,
            "font_family": font_family,
            "font_size": font_size,
            "text_color": text_color,
            "background_color": background_color,
            "text_align": text_align,
            "plugin_settings": settings
        }
        
        image = self.render_image(dimensions, "text_render.html", "text_render.css", image_template_params)

        return image
