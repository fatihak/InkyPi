import math
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


def _teardrop_points(cx: float, cy: float, size: float, n: int = 14) -> list[tuple[float, float]]:
    """A single closed outline (tip + a ~170deg arc for the bulb) so filled and
    outline-only draws both come from one continuous shape - two separately
    drawn pieces (e.g. an ellipse + a triangle) leave a visible seam line
    across the outline-only case where their edges don't coincide."""
    r = size * 0.35
    bulb_cy = cy + size * 0.15
    tip = (cx, cy - size * 0.5)
    start_deg, end_deg = 5, 175  # tangent points either side of the bulb's bottom
    points = [tip]
    for i in range(n + 1):
        deg = math.radians(start_deg + (end_deg - start_deg) * i / n)
        points.append((cx + r * math.cos(deg), bulb_cy + r * math.sin(deg)))
    return points


def _draw_droplet(draw: ImageDraw.ImageDraw, cx: float, cy: float, size: float, filled: bool, color):
    points = _teardrop_points(cx, cy, size)
    if filled:
        draw.polygon(points, fill=color)
    else:
        draw.polygon(points, outline=color, width=2)


def draw_humidity_drops(image: Image.Image, region, filled_count: int, total: int = 5):
    """5 drops in a 3-over-2 layout, border always visible, filled up to filled_count."""
    draw = ImageDraw.Draw(image)
    cx, cy = region.center
    drop_size = region.h * 0.58
    spacing = drop_size * 0.52
    row1_y = cy - region.h * 0.16
    row2_y = cy + region.h * 0.22

    def row_positions(count, y):
        start_x = cx - spacing * (count - 1) / 2
        return [(start_x + i * spacing, y) for i in range(count)]

    positions = row_positions(3, row1_y) + row_positions(2, row2_y)
    for i, (x, y) in enumerate(positions):
        _draw_droplet(draw, x, y, drop_size, i < filled_count, HUMIDITY_COLOR)
