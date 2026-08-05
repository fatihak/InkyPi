import os
from PIL import Image, ImageDraw, ImageFont

HUMIDITY_COLOR = (13, 71, 161)


class AssetStore:
    def __init__(self, icon_dir: str, font_dir: str):
        self.icon_dir = icon_dir
        self.font_dir = font_dir
        self._icon_cache = {}
        self._resized_cache = {}
        self._font_cache = {}

    def icon(self, key: str, size: tuple[int, int] | None = None) -> Image.Image | None:
        img = self._icon_cache.get(key)
        if img is None:
            path = os.path.join(self.icon_dir, f"{key}.png")
            if not os.path.exists(path):
                return None
            img = Image.open(path).convert("RGBA")
            self._icon_cache[key] = img
        if size is None:
            return img
        cache_key = (key, size)
        resized = self._resized_cache.get(cache_key)
        if resized is None:
            resized = img.resize(size, Image.LANCZOS)
            self._resized_cache[cache_key] = resized
        return resized

    def font(self, weight: str, size_px: int) -> ImageFont.FreeTypeFont:
        cache_key = (weight, size_px)
        font = self._font_cache.get(cache_key)
        if font is None:
            filename = "Jost-SemiBold.ttf" if weight == "bold" else "Jost.ttf"
            font = ImageFont.truetype(os.path.join(self.font_dir, filename), size_px)
            self._font_cache[cache_key] = font
        return font


def _draw_droplet(draw: ImageDraw.ImageDraw, cx: float, cy: float, w: float, filled: bool, color):
    r = w * 0.42
    bulb_cy = cy + w * 0.15
    bbox = [cx - r, bulb_cy - r, cx + r, bulb_cy + r]
    tip = [(cx, cy - w * 0.55), (cx - r * 0.9, bulb_cy - r * 0.15), (cx + r * 0.9, bulb_cy - r * 0.15)]
    if filled:
        draw.ellipse(bbox, fill=color)
        draw.polygon(tip, fill=color)
    else:
        draw.ellipse(bbox, outline=color, width=2)
        draw.polygon(tip, outline=color, width=2)


def draw_humidity_drops(image: Image.Image, region, filled_count: int, total: int = 5):
    """5 drops in a 3-over-2 layout, border always visible, filled up to filled_count."""
    draw = ImageDraw.Draw(image)
    cx, cy = region.center
    drop_w = region.h * 0.42
    spacing = drop_w * 0.72
    row1_y = cy - region.h * 0.15
    row2_y = cy + region.h * 0.22

    def row_positions(count, y):
        start_x = cx - spacing * (count - 1) / 2
        return [(start_x + i * spacing, y) for i in range(count)]

    positions = row_positions(3, row1_y) + row_positions(2, row2_y)
    for i, (x, y) in enumerate(positions):
        _draw_droplet(draw, x, y, drop_w, i < filled_count, HUMIDITY_COLOR)
