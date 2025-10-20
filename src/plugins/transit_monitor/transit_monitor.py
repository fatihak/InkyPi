from ..base_plugin.base_plugin import BasePlugin
from PIL import Image

class TransitMonitor(BasePlugin):
    def generate_image(self, settings, device_config):
        return Image.new("RGB", (400, 300), "white")