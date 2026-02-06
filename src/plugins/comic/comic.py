from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageDraw, ImageFont
import logging

from .comic_parser import COMICS, get_panel
from utils.app_utils import get_font

logger = logging.getLogger(__name__)

class Comic(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['comics'] = list(COMICS)
        return template_params

    def generate_image(self, settings, device_config):
        logger.info("=== Comic Plugin: Starting image generation ===")

        comic = settings.get("comic")
        if not comic or comic not in COMICS:
            logger.error(f"Invalid comic: {comic}")
            raise RuntimeError("Invalid comic provided.")

        logger.info(f"Fetching comic: {comic}")

        is_caption = settings.get("titleCaption") == "true"
        caption_font_size = settings.get("fontSize")

        logger.debug(f"Settings: show_caption={is_caption}, font_size={caption_font_size}")

        logger.debug("Parsing comic panel...")
        comic_panel = get_panel(comic)
        logger.info(f"Comic panel URL: {comic_panel.get('image_url', 'Unknown')}")

        if comic_panel.get("title"):
            logger.debug(f"Comic title: {comic_panel['title']}")
        if comic_panel.get("caption"):
            logger.debug(f"Comic caption: {comic_panel['caption']}")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
            logger.debug(f"Vertical orientation detected, dimensions: {dimensions[0]}x{dimensions[1]}")

        width, height = dimensions

        logger.debug("Composing comic image with captions...")
        image = self._compose_image(comic_panel, is_caption, caption_font_size, width, height)

        logger.info("=== Comic Plugin: Image generation complete ===")
        return image

    def _compose_image(self, comic_panel, is_caption, caption_font_size, width, height):
        # Use adaptive loader for memory-efficient processing
        # Note: Comic images are usually reasonable size, but still benefit from optimization
        img = self.image_loader.from_url(
            comic_panel["image_url"],
            dimensions=(width, height),
            resize=False  # We'll handle custom sizing below
        )

        if not img:
            raise RuntimeError("Failed to load comic image")

        with img:
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
