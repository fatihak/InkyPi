from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageDraw, ImageFont

import requests

from .comic_parser import COMICS, get_panel
from utils.app_utils import get_font

class Comic(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['comics'] = list(COMICS)
        return template_params

    def generate_image(self, settings, device_config):
        comic = settings.get("comic")
        if not comic or comic not in COMICS:
            raise RuntimeError("Invalid comic provided.")

        is_caption = settings.get("titleCaption") == "true"
        caption_font_size = settings.get("fontSize")

        comic_panel = get_panel(comic)

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        width, height = dimensions

        return self._compose_image(comic_panel, is_caption, caption_font_size, width, height)

    def _compose_image(self, comic_panel, is_caption, caption_font_size, width, height):
        response = requests.get(comic_panel["image_url"], stream=True)
        response.raise_for_status()

        with Image.open(response.raw) as img:
            background = Image.new("RGB", (width, height), "white")
            font = get_font("Jost", font_size=int(caption_font_size))
            draw = ImageDraw.Draw(background)
            top_padding, bottom_padding = 0, 0

            if is_caption:
                if comic_panel["title"]:
                    lines, wrapped_text = self._wrap_text(comic_panel["title"], font, width)
                    draw.multiline_text((width // 2, 0), wrapped_text, font=font, fill="black", anchor="ma")
                    top_padding = font.getbbox(wrapped_text)[3] * lines + 1

                if comic_panel["caption"]:
                    lines, wrapped_text = self._wrap_text(comic_panel["caption"], font, width)
                    draw.multiline_text((width // 2, height), wrapped_text, font=font, fill="black", anchor="md")
                    bottom_padding = font.getbbox(wrapped_text)[3] * lines + 1

            scale = min(width / img.width, (height - top_padding - bottom_padding) / img.height)
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.LANCZOS)

            y_middle = (height - img.height) // 2
            y_top_bound = top_padding
            y_bottom_bound = height - img.height - bottom_padding
            
            x = (width - img.width) // 2
            y = y = min(max(y_middle, y_top_bound), y_bottom_bound)
            
            background.paste(img, (x, y))

            return background

    def _wrap_text(self, text, font, width):
        lines = []
        words = text.split()[::-1]

        while words:
            line = words.pop()
            while words and font.getbbox(line + ' ' + words[-1])[2] < width:
                line += ' ' + words.pop()
            lines.append(line)

        return len(lines), '\n'.join(lines)
