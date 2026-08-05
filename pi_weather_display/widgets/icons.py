import os
from PIL import Image, ImageFont

# width / height of the source humidity_drop_filled.png / humidity_drop_empty.png
# assets (cropped from a pi4-app render - see pi_weather_display/TODO.md)
DROPLET_ASPECT = 28 / 38


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
            raw = Image.open(path).convert("RGBA")
            # Source PNGs carry wildly inconsistent transparent padding (some
            # fill their whole 512x512 canvas, some leave >20% margin) -
            # cropping to actual content first is what makes a uniform resize
            # below produce consistent-looking icons instead of some reading
            # bigger/smaller or off-center than others.
            bbox = raw.getbbox()
            img = raw.crop(bbox) if bbox else raw
            self._icon_cache[key] = img
        if size is None:
            return img
        cache_key = (key, size)
        resized = self._resized_cache.get(cache_key)
        if resized is None:
            target_w, target_h = size
            scale = min(target_w / img.width, target_h / img.height)
            fit_w, fit_h = max(1, round(img.width * scale)), max(1, round(img.height * scale))
            fitted = img.resize((fit_w, fit_h), Image.LANCZOS)
            resized = Image.new("RGBA", size, (0, 0, 0, 0))
            resized.paste(fitted, ((target_w - fit_w) // 2, (target_h - fit_h) // 2), fitted)
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


def draw_humidity_drops(image: Image.Image, region, assets: AssetStore, filled_count: int, total: int = 5):
    """5 drops in a 3-over-2 layout, border always visible, filled up to filled_count.
    Uses pre-rendered drop images (humidity_drop_filled/empty.png) rather than
    drawing the teardrop shape - a hand-drawn polygon approximation never
    looked as clean as the original CSS/SVG-rendered shape."""
    cx, cy = region.center
    drop_h = max(1, int(region.h * 0.5))
    drop_w = max(1, int(drop_h * DROPLET_ASPECT))
    spacing = drop_w

    filled_icon = assets.icon("humidity_drop_filled", (drop_w, drop_h))
    empty_icon = assets.icon("humidity_drop_empty", (drop_w, drop_h))

    row1_y = cy - region.h * 0.16
    row2_y = cy + region.h * 0.22

    def row_positions(count, y):
        start_x = cx - spacing * (count - 1) / 2
        return [(start_x + i * spacing, y) for i in range(count)]

    positions = row_positions(3, row1_y) + row_positions(2, row2_y)
    for i, (x, y) in enumerate(positions):
        icon = filled_icon if i < filled_count else empty_icon
        if icon:
            image.paste(icon, (int(x - drop_w / 2), int(y - drop_h / 2)), icon)
