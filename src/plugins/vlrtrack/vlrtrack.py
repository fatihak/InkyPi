from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageDraw, ImageFont
import requests
import logging
from bs4 import BeautifulSoup
import datetime
import json
import os
from io import BytesIO

logger = logging.getLogger(__name__)

from plugins.base_plugin.base_plugin import BasePlugin
from utils.image_utils import take_screenshot

from .vlrparser import getGames


class vlrtrack(BasePlugin):
    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        game_data = getGames()
        
        # Use sunset.jpg as background
        image = Image.open(os.path.join(os.path.dirname(__file__), "background.jpg")).convert("RGBA")
        draw = ImageDraw.Draw(image)

                
        title_font = ImageFont.truetype(os.path.join(os.path.dirname(__file__), "Tungsten-Bold.ttf"), 65)
        date_font = ImageFont.truetype(os.path.join(os.path.dirname(__file__), "Tungsten-Bold.ttf"),40)

        # Paste 1st logo and draws outline
        draw.rectangle([(88, 113), (261, 286)], outline="white", width=3, fill= (30, 30, 30))

        logo_url = game_data["team1_logo"]
        output_path = "output1.png"

        response = requests.get(logo_url)

        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            print(f"Image saved as {output_path}")
            logo_img = Image.open(BytesIO(response.content)).convert("RGBA")
            logo_img.thumbnail((150, 150))
            
            image.paste(logo_img, (100, 125), logo_img)
        else:
            print(f"Failed to download image, status code: {response.status_code}")

        # Paste 2nd logo and draws outline
        draw.rectangle([(538, 113), (712, 286)], outline="white", width=3, fill= (30, 30, 30))
        
        logo_url = game_data["team2_logo"]
        output_path = "output2.png"

        response = requests.get(logo_url)

        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            print(f"Image saved as {output_path}")
            logo_img = Image.open(BytesIO(response.content)).convert("RGBA")
            logo_img.thumbnail((150, 150))

            image.paste(logo_img, (550, 125), logo_img)
        else:
            print(f"Failed to download image, status code: {response.status_code}")
        
        # Paste date and team names
        draw.text((400, 30), game_data["unix_timestamp"], fill="white", font=title_font, anchor="mt")
        draw.text((175, 300), f"{game_data['team1']}", fill="white", font=title_font, anchor="mt")
        draw.text((625, 300), f"{game_data['team2']}", fill="white", font=title_font, anchor="mt")
        
        return image