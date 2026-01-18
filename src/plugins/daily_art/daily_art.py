import random
from io import BytesIO

import requests

from PIL import Image
from plugins.base_plugin.base_plugin import BasePlugin

# Define the base URL for the API
base_url = 'https://api.artic.edu/api/v1'

# Define the endpoint you want to query (for example, artworks)
endpoint = '/artworks'
search = '/search?q=painting'
# Construct the full URL
url = f'{base_url}{endpoint}'
search_url = f'{url}{search}'

class DailyArt(BasePlugin):
    def generate_image(self, settings, device_config):
        # Send a GET request to the API
        response = requests.get(url, params={'limit': 0})
        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            data = response.json()  # Parse the JSON response
            total = data['pagination']['total_pages']
            page_no = random.randint(0, total)

            response = requests.get(url, params={'page': page_no, 'limit': 10})
            if response.status_code == 200:
                width = device_config.get_resolution()[0]
                page_data = response.json()
                iiif_url = page_data['config']['iiif_url']
                artwork = random.choice(page_data['data'])
                artwork_id = artwork['image_id']
                artwork_url = f'{iiif_url}/{artwork_id}/full/843,/0/default.jpg'
                response = requests.get(artwork_url)
                if response.status_code == 200:
                    img = Image.open(BytesIO(response.content))
                    img.show()  # Opens the image in the default viewer
                    return img
                else:
                    print("Failed to load image.")
            else:
                print(f"Error: {response.status_code}")
        else:
            print(f"Error: {response.status_code}")

        pass