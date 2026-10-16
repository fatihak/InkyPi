from plugins.base_plugin.base_plugin import BasePlugin
from layout_manager import (
    PIP_CORNERS, Region, compose, compute_pip_region, get_canvas_size,
    parse_instance_ref, render_plugin_instance,
)
import logging

logger = logging.getLogger(__name__)

DEFAULT_CORNER = "top-right"
DEFAULT_SIZE_PERCENT = 35
DEFAULT_MARGIN = 10
DEFAULT_BORDER_WIDTH = 2
DEFAULT_RENDER_MODE = "scale"


class PictureInPicture(BasePlugin):
    """Layout plugin that draws one saved plugin instance full screen and a second,
    smaller instance over the top of it in a chosen corner."""

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['corners'] = PIP_CORNERS
        return template_params

    def generate_image(self, settings, device_config):
        background_ref = settings.get('background')
        overlay_ref = settings.get('overlay')
        for ref in (background_ref, overlay_ref):
            if parse_instance_ref(ref)[0] == self.get_plugin_id():
                raise RuntimeError("Picture in Picture layouts cannot be nested.")

        corner = settings.get('corner') or DEFAULT_CORNER
        size_percent = _to_number(settings.get('overlaySize'), DEFAULT_SIZE_PERCENT)
        margin = _to_number(settings.get('margin'), DEFAULT_MARGIN)
        border_width = _to_number(settings.get('borderWidth'), DEFAULT_BORDER_WIDTH)

        canvas_size = get_canvas_size(device_config)
        background_region = Region(0, 0, *canvas_size)
        overlay_region = compute_pip_region(canvas_size, corner, size_percent, margin)

        background = render_plugin_instance(device_config, background_ref, background_region.size)
        # "scale" renders the overlay full screen and shrinks it, so fixed-size layouts aren't
        # clipped; "native" renders at the overlay size for plugins whose layout adapts to it
        render_mode = settings.get('renderMode') or DEFAULT_RENDER_MODE
        overlay_render_size = canvas_size if render_mode == "scale" else overlay_region.size
        overlay = render_plugin_instance(device_config, overlay_ref, overlay_region.size, overlay_render_size)

        return compose(
            canvas_size,
            [(background, background_region), (overlay, overlay_region)],
            border_width=int(border_width),
        )


def _to_number(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
