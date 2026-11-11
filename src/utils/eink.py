"""Colour rendering for limited-palette e-paper displays (e.g. Inky Spectra 6).

Two rendering modes:

- "photo": Floyd-Steinberg dithering towards the inks as they really look (measured
  palette, relative to the paper white), after lifting the midtones a little. Colours
  stay faithful (a green sofa stays green) instead of being washed out.
- "classic": the driver's own conversion (dithering towards a palette blended by the
  "Inky Driver Saturation" setting), available in manual mode.
- "graphics": tuned for UI-like images (weather, calendar, text):
    1. colours are adapted to the inks that will render them: coloured pixels are
       saturated, and darkened according to how dark the matching ink really is
       (measured palette) - pastel blue becomes a readable blue, yellow stays light;
    2. pixels already close to an ink are snapped onto it (crisp text and backgrounds,
       no red fringes from dithered anti-aliasing);
    3. ordered (Bayer) dithering: regular patterns instead of noisy error diffusion on
       flat areas.
  The result only contains the display's pure colours, so the driver sends it as is.

A display palette is described by:
    pure:     the colours the driver expects (what each ink is called in RGB)
    measured: what each ink actually looks like (used to adapt colours and to simulate)
"""

import colorsys
import inspect
import logging
import re

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

PHOTO, GRAPHICS, MANUAL = "photo", "graphics", "manual"
CLASSIC = "classic"  # the driver's own dithering (former photo rendering), manual mode only
MODES = (PHOTO, GRAPHICS, MANUAL)
RENDERINGS = (PHOTO, GRAPHICS, CLASSIC)

# Photo rendering: midtones lifted (the inks are darker than a screen) and a little more
# saturation, chosen by comparing variants side by side on a Spectra 6 panel.
PHOTO_GAMMA = 0.75
PHOTO_SATURATION = 1.15

# Manual mode: per-instance values replacing the global image settings
MANUAL_FIELDS = {"saturation": "colourSaturation", "contrast": "colourContrast",
                 "brightness": "colourBrightness", "sharpness": "colourSharpness"}
# Settings that only change how an image is rendered on the panel, not the plugin's output
RENDER_FIELDS = {"colourMode", "colourRendering", "colourInk", *MANUAL_FIELDS.values()}

# Plugins that show photographs: everything else is rendered as graphics in auto mode.
PHOTO_PLUGINS = {"image_folder", "image_upload", "image_album", "image_url", "google_photos",
                 "unsplash", "apod", "wpotd", "ai_image", "comic", "screenshot", "newspaper",
                 "clock"}  # clock faces are mostly gradients

# Inky Spectra 6 (E673 etc.) palettes, used to simulate a display in development
SPECTRA6 = {
    "pure": [[0, 0, 0], [255, 255, 255], [255, 255, 0], [255, 0, 0], [0, 0, 255], [0, 255, 0]],
    "measured": [[0, 0, 0], [161, 164, 165], [208, 190, 71], [156, 72, 75], [61, 59, 94], [58, 91, 70]],
}

_BAYER8 = (np.array([
    [0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
    [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]], dtype=np.float32) + 0.5) / 64.0 - 0.5


def default_mode(plugin_id):
    """Recommended rendering for a plugin: photo for photographs, graphics for everything else."""
    return PHOTO if plugin_id in PHOTO_PLUGINS else GRAPHICS


def resolve_mode(plugin_id, settings):
    """Rendering algorithm of a plugin instance (photo or graphics)."""
    settings = settings or {}
    mode = settings.get("colourMode")
    if mode == MANUAL:
        rendering = settings.get("colourRendering")
        return rendering if rendering in RENDERINGS else default_mode(plugin_id)
    return mode if mode in (PHOTO, GRAPHICS) else default_mode(plugin_id)


def _number(value, default, low, high):
    try:
        return min(high, max(low, float(value)))
    except (TypeError, ValueError):
        return default


def colour_plan(plugin_id, settings, image_settings):
    """How to render an instance: algorithm, image enhancement and ink saturation.

    In manual mode the instance's own values replace the global image settings.
    """
    settings = settings or {}
    image_settings = dict(image_settings or {})
    saturation = _number(image_settings.get("inky_saturation"), 0.5, 0.0, 1.0)
    manual = settings.get("colourMode") == MANUAL
    if manual:
        for key, field in MANUAL_FIELDS.items():
            image_settings[key] = _number(settings.get(field), _number(image_settings.get(key), 1.0, 0.0, 2.0), 0.0, 2.0)
        saturation = _number(settings.get("colourInk"), saturation, 0.0, 1.0)
        image_settings["inky_saturation"] = saturation
    return {"mode": resolve_mode(plugin_id, settings), "enhance": image_settings,
            "saturation": saturation, "manual": manual}


def palette_from_inky(inky_display):
    """Describes an Inky driver's palette, or None if it has no pure-colour (no dither) path.

    Spectra drivers skip their own dithering for palette images with exactly N colours
    ("if len(image.palette.colors) == N"); that N and the driver's palettes are read
    from the driver itself.
    """
    module = inspect.getmodule(type(inky_display))
    pure = getattr(module, "DESATURATED_PALETTE", None)
    measured = getattr(module, "SATURATED_PALETTE", None)
    try:
        source = inspect.getsource(type(inky_display).set_image)
    except (AttributeError, OSError, TypeError):
        return None
    match = re.search(r"len\(image\.palette\.colors\)\s*==\s*(\d+)", source)
    if not (pure and measured and match):
        return None
    count = int(match.group(1))
    if len(pure) < count or len(measured) < count:
        return None
    return {"pure": [list(c) for c in pure[:count]], "measured": [list(c) for c in measured[:count]]}


def blended(palette, saturation):
    """The driver's quantization palette for a given 'saturation' (pure <-> measured)."""
    pure = np.array(palette["pure"], dtype=np.float32)
    measured = np.array(palette["measured"], dtype=np.float32)
    return measured * saturation + pure * (1.0 - saturation)


def _white_index(palette):
    pure = np.array(palette["pure"])
    return int(np.argmax(pure.sum(axis=1)))


def adapt_colours(image, palette, strength=0.4, boost=1.7, min_chroma=24):
    """Saturate coloured pixels and darken them as much as the ink that will render them
    is darker than the paper. Neutral pixels (white, greys, black) are left unchanged."""
    measured = np.array(palette["measured"], dtype=np.float32)
    white = measured[_white_index(palette)]
    white_luma = float(white @ [0.299, 0.587, 0.114]) or 255.0

    # Hue and relative darkness of each chromatic ink
    inks = []
    for rgb in measured:
        h, s, v = colorsys.rgb_to_hsv(*(rgb / 255.0))
        if s < 0.15:
            continue  # black / white
        darkness = max(0.0, 1.0 - float(rgb @ [0.299, 0.587, 0.114]) / white_luma)
        inks.append((h * 360.0, darkness))
    if not inks:
        return image

    hsv = np.asarray(image.convert("HSV"), dtype=np.float32) / 255.0
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    chroma = rgb.max(-1) - rgb.min(-1)
    weight = np.clip((chroma - min_chroma) / 40.0, 0, 1)

    # Darkness expected at each hue: interpolated between the two closest inks
    hue = hsv[..., 0] * 360.0
    ink_hues = np.array([h for h, _ in inks], dtype=np.float32)
    ink_dark = np.array([d for _, d in inks], dtype=np.float32)
    dist = np.abs(((hue[..., None] - ink_hues[None, None, :]) + 180.0) % 360.0 - 180.0)
    inv = 1.0 / (dist + 1.0) ** 2
    darkness = (inv * ink_dark).sum(-1) / inv.sum(-1)

    hsv[..., 1] = np.clip(hsv[..., 1] * (1 + (boost - 1) * weight), 0, 1)
    hsv[..., 2] = hsv[..., 2] * (1 - strength * darkness * weight * 1.6)
    return Image.fromarray((np.clip(hsv, 0, 1) * 255).astype(np.uint8), "HSV").convert("RGB")


def _distances(rgb, quant_palette):
    """Squared distance of each pixel to each palette colour (|x|^2 - 2x.p + |p|^2, BLAS-fast)."""
    pal = quant_palette.astype(np.float32)
    dist = rgb @ (-2.0 * pal.T)
    dist += (pal ** 2).sum(-1)
    dist += (rgb ** 2).sum(-1, keepdims=True)
    return dist


def _snap(rgb, quant_palette, threshold=48):
    """Pixels within `threshold` of a quantization colour become exactly that colour."""
    dist = _distances(rgb, quant_palette)
    nearest = dist.argmin(-1)
    close = dist.min(-1) <= threshold ** 2
    out = rgb.copy()
    out[close] = quant_palette[nearest[close]]
    return out


def _neutral_inks(palette):
    """Indices of the achromatic inks (black, white): greys are dithered with these only."""
    measured = np.array(palette["measured"], dtype=np.float32)
    return [i for i, rgb in enumerate(measured) if colorsys.rgb_to_hsv(*(rgb / 255.0))[1] < 0.15]


def _ordered_indices(rgb, quant_palette, neutral_inks=(), spread=96.0, neutral_chroma=24):
    h, w, _ = rgb.shape
    threshold = np.tile(_BAYER8, (h // 8 + 1, w // 8 + 1))[:h, :w][..., None] * spread
    shifted = rgb + threshold
    neutral = (rgb.max(-1) - rgb.min(-1)) < neutral_chroma
    chromatic = np.ones(len(quant_palette), dtype=bool)
    chromatic[list(neutral_inks)] = False
    shifted = shifted.astype(np.float32)
    indices = np.empty((h, w), dtype=np.uint8)
    for y0 in range(0, h, 120):  # bounded memory: distances for a band of rows at a time
        band = shifted[y0:y0 + 120]
        dist = _distances(band, quant_palette)
        if len(neutral_inks) >= 2:
            # grey pixels are made of black and white dots only (no coloured speckles)
            dist[neutral[y0:y0 + 120][..., None] & chromatic[None, None, :]] = np.inf
        indices[y0:y0 + 120] = dist.argmin(-1)
    return indices


def _sharpen_edges(indices, pixels, rgb, palette, neutral_inks, edge_range=64, text_threshold=170,
                   neutral_chroma=24):
    """Text and thin lines: grey anti-aliasing pixels on an edge become black or white.

    Dithering them would give isolated dots, which e-paper renders poorly (thin, broken
    letters). A threshold above mid-grey keeps strokes slightly bolder, like on paper.
    """
    if len(neutral_inks) < 2:
        return indices
    measured = np.array(palette["measured"], dtype=np.float32)
    luma_of = lambda c: c @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    black = min(neutral_inks, key=lambda i: luma_of(measured[i]))
    white = max(neutral_inks, key=lambda i: luma_of(measured[i]))
    grey = Image.fromarray(pixels).convert("L")
    local_range = (np.asarray(grey.filter(ImageFilter.MaxFilter(3)), dtype=np.int16)
                   - np.asarray(grey.filter(ImageFilter.MinFilter(3)), dtype=np.int16))
    neutral = (rgb.max(-1) - rgb.min(-1)) < neutral_chroma
    edge = neutral & (local_range > edge_range)
    luma = np.asarray(grey, dtype=np.int16)
    out = indices.copy()
    out[edge] = np.where(luma[edge] < text_threshold, black, white)
    return out


def render_indices(image, palette, mode, saturation=0.5):
    """Palette indices (one per pixel) as the display will show them."""
    quant = blended(palette, saturation)
    if mode == GRAPHICS:
        # Adapting and snapping depend on the colour only: done once per distinct colour
        pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
        packed = (pixels[..., 0].astype(np.uint32) << 16) | (pixels[..., 1].astype(np.uint32) << 8) | pixels[..., 2]
        colours, inverse = np.unique(packed.ravel(), return_inverse=True)
        unique_rgb = np.stack([(colours >> 16) & 255, (colours >> 8) & 255, colours & 255], -1).astype(np.uint8)
        adapted = adapt_colours(Image.fromarray(unique_rgb[None, :, :], "RGB"), palette)
        snapped = _snap(np.asarray(adapted, dtype=np.float32), quant)[0]
        rgb = snapped[inverse.ravel()].reshape(pixels.shape)
        neutral_inks = _neutral_inks(palette)
        indices = _ordered_indices(rgb, quant, neutral_inks)
        return _sharpen_edges(indices, pixels, rgb, palette, neutral_inks)
    image = image.convert("RGB")
    if mode == PHOTO:
        quant = perceived_palette(palette)
        lift = [round(255 * (i / 255) ** PHOTO_GAMMA) for i in range(256)] * 3
        image = ImageEnhance.Color(image.point(lift)).enhance(PHOTO_SATURATION)
    pal_image = Image.new("P", (1, 1))
    pal_image.putpalette([int(v) for v in np.asarray(quant).flatten()])
    quantized = image.quantize(len(quant), palette=pal_image, dither=Image.Dither.FLOYDSTEINBERG)
    return np.asarray(quantized, dtype=np.uint8)


def to_pure_palette_image(indices, palette):
    """Palette ("P") image in the display's pure colours: the driver sends it without dithering."""
    image = Image.fromarray(indices.astype(np.uint8), "P")
    image.putpalette([int(v) for colour in palette["pure"] for v in colour])
    return image


def perceived_palette(palette):
    """The inks as the eye sees them: measured colours relative to the paper white."""
    measured = np.array(palette["measured"], dtype=np.float32)
    white = measured[_white_index(palette)]
    return np.clip(measured / np.maximum(white, 1) * 255.0, 0, 255)


def simulate(image, palette, mode, saturation=0.5):
    """What the panel will look like (measured ink colours, normalised to the paper white)."""
    indices = render_indices(image, palette, mode, saturation)
    return Image.fromarray(perceived_palette(palette).astype(np.uint8)[indices], "RGB")
