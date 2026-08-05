"""Circular gauge widgets (wind compass, barometer, UV, AQI). Each render_*
function draws onto its own small RGBA image sized to match the original
weather.html SVG's viewBox, which canvas.py then scales/pastes into place -
this keeps the coordinates here a near-direct port of the SVG paths."""

import math
from PIL import Image, ImageDraw


def rotate_points(points, center, angle_deg):
    """Matches CSS `transform: rotate(angle_deg)` around center, in screen (y-down) coords."""
    cx, cy = center
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    out = []
    for x, y in points:
        dx, dy = x - cx, y - cy
        out.append((cx + dx * cos_t - dy * sin_t, cy + dx * sin_t + dy * cos_t))
    return out


def _dashed_line(draw, p1, p2, color, width, dash=4, gap=7):
    x1, y1 = p1
    x2, y2 = p2
    length = math.hypot(x2 - x1, y2 - y1)
    if length == 0:
        return
    dx, dy = (x2 - x1) / length, (y2 - y1) / length
    pos = 0.0
    while pos < length:
        seg_end = min(pos + dash, length)
        draw.line([(x1 + dx * pos, y1 + dy * pos), (x1 + dx * seg_end, y1 + dy * seg_end)], fill=color, width=width)
        pos += dash + gap


def _dashed_circle(draw, center, radius, color, width, dash=4, gap=7):
    cx, cy = center
    circumference = 2 * math.pi * radius
    total = 0.0
    while total < circumference:
        a0 = math.degrees(total / radius)
        a1 = math.degrees(min(total + dash, circumference) / radius)
        draw.arc([cx - radius, cy - radius, cx + radius, cy + radius], a0, a1, fill=color, width=width)
        total += dash + gap


def render_wind_compass(rotation_deg: float) -> Image.Image:
    size = (200, 180)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy, r = 100, 90, 75
    color = (26, 26, 26)

    _dashed_circle(draw, (cx, cy), r, color, width=5)
    for x1, y1, x2, y2 in [(100, 5, 100, 175), (15, 90, 185, 90), (160.1, 29.9, 39.9, 150.1), (39.9, 29.9, 160.1, 150.1)]:
        _dashed_line(draw, (x1, y1), (x2, y2), color, width=5)

    needle = rotate_points([(100, 20), (116, 125), (100, 119), (84, 125)], (cx, cy), rotation_deg)
    draw.polygon(needle, fill=(183, 28, 28))
    draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=(255, 255, 255))
    return img


def _round_cap(draw, point, width, color):
    x, y = point
    r = width / 2
    draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


def render_pressure_gauge(rotation_deg: float) -> Image.Image:
    size = (200, 150)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy, r = 100, 110, 85
    color = (13, 71, 161)
    a, b = (20.1, 139.07), (179.9, 139.07)

    # dome arc through the top (the "long way" between a and b), plus a flat bottom line
    draw.arc([cx - r, cy - r, cx + r, cy + r], 160, 380, fill=color, width=11)
    draw.line([a, b], fill=color, width=11)
    _round_cap(draw, a, 11, color)
    _round_cap(draw, b, 11, color)

    for x1, y1, x2, y2 in [
        (15, 110, 28, 110), (26.4, 67.5, 37.6, 74), (57.5, 36.4, 64, 47.6), (100, 25, 100, 38),
        (142.5, 36.4, 136, 47.6), (173.6, 67.5, 162.4, 74), (185, 110, 172, 110),
    ]:
        draw.line([(x1, y1), (x2, y2)], fill=color, width=7)
        _round_cap(draw, (x1, y1), 7, color)
        _round_cap(draw, (x2, y2), 7, color)

    # rain (low pressure) - translate(45,100) scale(1.25)
    def tr(x, y):
        return (45 + x * 1.25, 100 + y * 1.25)
    rain_color = (26, 74, 122)
    for cx_, cy_, rx, ry in [(-4, 0, 4.5, 3.5), (2, -2, 5.5, 4.5), (8, 0, 3.5, 3)]:
        x, y = tr(cx_, cy_)
        draw.ellipse([x - rx * 1.25, y - ry * 1.25, x + rx * 1.25, y + ry * 1.25], fill=rain_color)
    rx0, ry0 = tr(-7.5, 0)
    rx1, ry1 = tr(-7.5 + 19, 0 + 4.5)
    draw.rounded_rectangle([rx0, ry0, rx1, ry1], radius=3, fill=rain_color)
    for x1, y1, x2, y2 in [(-3, 7, -5, 11), (2, 7, 0, 11), (7, 7, 5, 11)]:
        draw.line([tr(x1, y1), tr(x2, y2)], fill=rain_color, width=3)

    # cloud (mid pressure) - translate(100,56) scale(1.25)
    def tc(x, y):
        return (100 + x * 1.25, 56 + y * 1.25)
    cloud_color = (92, 92, 92)
    for cx_, cy_, rx, ry in [(-4, 1, 5, 4), (3, -1, 6, 5), (9, 1, 4, 3.5)]:
        x, y = tc(cx_, cy_)
        draw.ellipse([x - rx * 1.25, y - ry * 1.25, x + rx * 1.25, y + ry * 1.25], fill=cloud_color)
    cx0, cy0 = tc(-8, 1)
    cx1, cy1 = tc(-8 + 21, 1 + 5)
    draw.rounded_rectangle([cx0, cy0, cx1, cy1], radius=3, fill=cloud_color)

    # sun (high pressure) - translate(155,100) scale(1.25)
    def ts(x, y):
        return (155 + x * 1.25, 100 + y * 1.25)
    sun_color = (245, 124, 0)
    sx, sy = ts(0, 0)
    draw.ellipse([sx - 7.5, sy - 7.5, sx + 7.5, sy + 7.5], fill=sun_color)
    for x1, y1, x2, y2 in [
        (0, -9, 0, -12), (0, 9, 0, 12), (-9, 0, -12, 0), (9, 0, 12, 0),
        (-6.4, -6.4, -8.5, -8.5), (6.4, 6.4, 8.5, 8.5), (-6.4, 6.4, -8.5, 8.5), (6.4, -6.4, 8.5, -8.5),
    ]:
        draw.line([ts(x1, y1), ts(x2, y2)], fill=sun_color, width=3)

    needle = rotate_points([(100, 40), (117, 98), (100, 89), (83, 98)], (cx, cy), rotation_deg)
    draw.polygon(needle, fill=(17, 17, 17), outline=(255, 255, 255), width=3)
    draw.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], fill=(17, 17, 17), outline=(255, 255, 255), width=3)
    return img


def render_uv_icon(uv_color_hex: str, uv_beams: list) -> Image.Image:
    size = (120, 120)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for beam in uv_beams:
        draw.polygon(beam, fill=uv_color_hex)
    draw.ellipse([36, 36, 84, 84], fill=uv_color_hex)
    return img


def render_aqi_gauge(rotation_deg: float) -> Image.Image:
    size = (200, 150)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy, r = 100, 120, 75
    bands = [
        (180, 225, (242, 80, 74)),
        (225, 270, (245, 163, 0)),
        (270, 315, (247, 198, 0)),
        (315, 360, (51, 168, 82)),
    ]
    for start, end, color in bands:
        draw.arc([cx - r, cy - r, cx + r, cy + r], start, end, fill=color, width=28)

    needle = rotate_points(
        [(100, 114), (140, 114), (140, 102), (168, 120), (140, 138), (140, 126), (100, 126)],
        (cx, cy), rotation_deg,
    )
    draw.polygon(needle, fill=(61, 61, 82))
    draw.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=(61, 61, 82))
    return img
