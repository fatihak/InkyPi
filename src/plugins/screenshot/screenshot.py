from plugins.base_plugin.base_plugin import BasePlugin
from utils.image_utils import take_screenshot
import logging

logger = logging.getLogger(__name__)

class Screenshot(BasePlugin):
    DEFAULT_RENDER_WAIT_MS = None

    def __init__(self, config, **dependencies):
        super().__init__(config, **dependencies)
        self._captured_image_cache = {}

    def generate_image(self, settings, device_config):
        cache_key = self._get_cache_key(settings, device_config)
        image = self._captured_image_cache.pop(cache_key, None)
        if image:
            return image

        image = self._capture_screenshot(settings, device_config)

        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")

        return image

    def skip_display_condition(self, settings, device_config, current_dt):
        skip_if_blank = settings.get('skipIfBlank')
        # Default to True if not specified, matching the UI default
        if skip_if_blank is not None and skip_if_blank not in (True, 'true'):
            return None

        image = self._capture_screenshot(settings, device_config)
        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")

        if self._is_single_color(image):
            return "Screenshot is blank"

        self._captured_image_cache[self._get_cache_key(settings, device_config)] = image
        return None

    def _capture_screenshot(self, settings, device_config):
        url = self._get_url(settings)
        if not url:
            raise RuntimeError("URL is required.")

        dimensions = self._get_screenshot_dimensions(device_config)
        virtual_time_budget_ms = self._get_virtual_time_budget_ms(settings)

        logger.info(f"Taking screenshot of url: {url}")

        return take_screenshot(url, dimensions, timeout_ms=40000, virtual_time_budget_ms=virtual_time_budget_ms)

    def _get_url(self, settings):
        return settings.get('url')

    def _get_screenshot_dimensions(self, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        return dimensions

    def _get_virtual_time_budget_ms(self, settings):
        render_wait_ms = settings.get('renderWaitMs')
        if render_wait_ms in (None, ''):
            render_wait_ms = self.DEFAULT_RENDER_WAIT_MS

        virtual_time_budget_ms = None
        if render_wait_ms:
            try:
                virtual_time_budget_ms = int(render_wait_ms)
            except (TypeError, ValueError):
                raise RuntimeError("Render wait must be a whole number of milliseconds.")

            if virtual_time_budget_ms < 0:
                raise RuntimeError("Render wait must be zero or greater.")
            if virtual_time_budget_ms == 0:
                virtual_time_budget_ms = None

        return virtual_time_budget_ms

    def _get_cache_key(self, settings, device_config):
        return (
            id(settings),
            self._get_url(settings),
            settings.get('renderWaitMs'),
            self._get_screenshot_dimensions(device_config),
        )

    def _is_single_color(self, image):
        return len(image.convert("RGBA").getcolors(maxcolors=2) or []) == 1
