import logging
from dataclasses import dataclass

from PIL import Image, ImageDraw

from plugins.plugin_registry import get_plugin_instance
from utils.image_utils import resize_image

logger = logging.getLogger(__name__)

PIP_CORNERS = ["top-left", "top-right", "bottom-left", "bottom-right"]
INSTANCE_REF_SEPARATOR = "/"


@dataclass
class Region:
    """A rectangular area of the display canvas, in pixels."""
    x: int
    y: int
    width: int
    height: int

    @property
    def size(self):
        return (self.width, self.height)

    @property
    def position(self):
        return (self.x, self.y)


class ResolutionOverride:
    """Wraps a device config so that plugins render at the size of a layout region.

    Plugins read their output size from device_config.get_resolution() and swap it when
    the device is in vertical orientation, so the override is stored pre-swap to match.
    Every other attribute is delegated to the wrapped config.
    """

    def __init__(self, device_config, region_size):
        self._device_config = device_config
        width, height = region_size
        if device_config.get_config("orientation") == "vertical":
            width, height = height, width
        self._resolution = (int(width), int(height))

    def get_resolution(self):
        return self._resolution

    def __getattr__(self, name):
        return getattr(self._device_config, name)


def get_canvas_size(device_config):
    """Returns the (width, height) plugins render at, accounting for orientation."""
    width, height = device_config.get_resolution()
    if device_config.get_config("orientation") == "vertical":
        return (height, width)
    return (width, height)


def compute_pip_region(canvas_size, corner, size_percent, margin=0):
    """Computes the overlay region for a picture-in-picture layout.

    The overlay keeps the canvas aspect ratio and is scaled to size_percent of the
    canvas width and height, then anchored to the given corner, inset by margin pixels.
    """
    if corner not in PIP_CORNERS:
        raise ValueError(f"Invalid corner '{corner}', expected one of {PIP_CORNERS}")

    size_percent = max(1, min(100, float(size_percent)))
    canvas_width, canvas_height = canvas_size

    width = max(1, round(canvas_width * size_percent / 100))
    height = max(1, round(canvas_height * size_percent / 100))

    # keep the margin from pushing the overlay off the canvas
    margin = max(0, int(margin))
    margin_x = min(margin, (canvas_width - width) // 2)
    margin_y = min(margin, (canvas_height - height) // 2)

    x = margin_x if corner.endswith("left") else canvas_width - width - margin_x
    y = margin_y if corner.startswith("top") else canvas_height - height - margin_y
    return Region(x, y, width, height)


def parse_instance_ref(instance_ref):
    """Splits a '<plugin_id>/<instance name>' reference into its parts."""
    if not instance_ref or INSTANCE_REF_SEPARATOR not in instance_ref:
        raise RuntimeError("A plugin instance must be selected.")
    plugin_id, instance_name = instance_ref.split(INSTANCE_REF_SEPARATOR, 1)
    return plugin_id, instance_name


def render_plugin_instance(device_config, instance_ref, region_size, render_size=None):
    """Generates the image for a saved plugin instance, sized to fit the region exactly.

    The plugin renders at render_size (defaults to region_size) and the result is scaled to
    the region. Rendering larger and scaling down keeps plugins with fixed-size layouts
    from being clipped when placed in a small region.
    """
    render_size = tuple(render_size or region_size)
    plugin_id, instance_name = parse_instance_ref(instance_ref)

    plugin_instance = device_config.get_playlist_manager().find_plugin(plugin_id, instance_name)
    if not plugin_instance:
        raise RuntimeError(f"Plugin instance '{instance_name}' ({plugin_id}) no longer exists.")

    plugin_config = device_config.get_plugin(plugin_id)
    if not plugin_config:
        raise RuntimeError(f"Plugin '{plugin_id}' not found.")

    plugin = get_plugin_instance(plugin_config)
    logger.info(f"Rendering layout region. | plugin_instance: '{instance_name}' | render_size: {render_size} | region_size: {region_size}")
    image = plugin.generate_image(plugin_instance.settings, ResolutionOverride(device_config, render_size))

    # plugins that display arbitrary images may not honour the requested size
    if image.size != tuple(region_size):
        image = resize_image(image, region_size, plugin_config.get("image_settings", []))
    return image


def compose(canvas_size, layers, border_width=0, border_color="black"):
    """Pastes (image, region) layers onto a canvas in order, so later layers sit on top.

    A border is drawn inside the edge of every layer after the first.
    """
    canvas = Image.new("RGB", canvas_size, "white")
    for index, (image, region) in enumerate(layers):
        canvas.paste(image.convert("RGB"), region.position)
        if index > 0 and border_width > 0:
            draw = ImageDraw.Draw(canvas)
            draw.rectangle(
                [region.x, region.y, region.x + region.width - 1, region.y + region.height - 1],
                outline=border_color,
                width=border_width,
            )
    return canvas
