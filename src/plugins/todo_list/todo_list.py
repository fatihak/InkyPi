from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
from io import BytesIO
import requests
import logging

logger = logging.getLogger(__name__)

FONT_SIZES = {
    "x-small": 0.7,
    "small": 0.9,
    "normal": 1,
    "large": 1.1,
    "x-large": 1.3
}

class TodoList(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        lists = []
        for title, raw_list in zip(settings['list-title[]'], settings['list[]']):
            elements = [line for line in raw_list.split('\n') if line.strip()]
            lists.append({
                'title': title,
                'elements': elements
            })

        template_params = {
            "title": settings.get('title'),
            "list_style": settings.get('listStyle', 'disc'),
            "font_scale": FONT_SIZES.get(settings.get('fontSize', 'normal'), 1),
            "lists": lists,
            "plugin_settings": settings
        }
        
        image = self.render_image(dimensions, "todo_list.html", "todo_list.css", template_params)
        return image