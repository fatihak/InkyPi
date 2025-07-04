import requests
from PIL import Image
from io import BytesIO
from flask import request, jsonify, render_template

from plugins.base_plugin.base_plugin import BasePlugin
from utils.image_utils import convert_to_grayscale

class UnsplashPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.search_term = ""
        self.access_key = self.read_api_key("UNSPLASH_ACCESS_KEY") # Assuming API key is stored as UNSPLASH_ACCESS_KEY

    def get_config_html(self, sess):
        return render_template(f'{self.plugin_name}/settings.html', search_term=self.search_term)

    def handle_config_post(self, sess):
        self.search_term = request.form.get('search_term', '')
        return jsonify({"status": "success", "message": "Unsplash search term updated."})

    def get_image(self):
        if not self.access_key:
            self.log_error("Unsplash API key not found.")
            return None

        if not self.search_term:
            self.log_warning("No search term provided for Unsplash.")
            return None

        url = f"https://api.unsplash.com/photos/random?query={self.search_term}&client_id={self.access_key}"

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            image_url = data['urls']['full']
            image_response = requests.get(image_url)
            image_response.raise_for_status()
            img = Image.open(BytesIO(image_response.content))
            return convert_to_grayscale(img)
        except requests.exceptions.RequestException as e:
            self.log_error(f"Error fetching image from Unsplash: {e}")
            return None
        except KeyError:
            self.log_error("Unexpected response format from Unsplash API.")
            return None

    def get_render_info(self, sess):
        # This plugin primarily provides an image, no complex rendering needed beyond the image display
        return {}

    def render_html(self, render_info):
        # This plugin doesn't render HTML content directly on the e-paper
        return ""

# Basic structure for plugin-info.json (needs to be created separately in the plugin directory)
"""
{
  "name": "Unsplash",
  "description": "Fetches random images from Unsplash based on a search term.",
  "version": "1.0",
  "config_dialog": true,
  "render_html": false
}
"""

# Basic structure for settings.html (needs to be created separately in the plugin directory)
"""
<!DOCTYPE html>
<html>
<head>
    <title>Unsplash Settings</title>
</head>
<body>
    <h1>Unsplash Plugin Settings</h1>
    <form id="settingsForm">
        <label for="search_term">Search Term:</label>
        <input type="text" id="search_term" name="search_term" value="{{ search_term }}">
        <button type="submit">Save</button>
    </form>

    <script>
        document.getElementById('settingsForm').addEventListener('submit', function(event) {
            event.preventDefault();
            const formData = new FormData(this);
            fetch('/plugin/Unsplash/settings', {
                method: 'POST',
                body: new URLSearchParams(formData)
            })
            .then(response => response.json())
            .then(data => {
                alert(data.message);
            });
        });
    </script>
</body>
</html>
"""