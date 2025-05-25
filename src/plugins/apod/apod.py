from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
from io import BytesIO
import requests
import logging

logger = logging.getLogger(__name__)

class Apod(BasePlugin):
    def generate_settings_template(self):
        # Store your API key with NASA_SECRET={API_KEY} in the .env file
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "NASA",
            "expected_key": "NASA_SECRET"
        }
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        logger.info(f"APOD plugin settings: {settings}")

        api_key = device_config.load_env_key("NASA_SECRET")
        if not api_key:
            raise RuntimeError("NASA API Key not configured.")

        date = settings.get("customDate")
        params = {"api_key": api_key}
        if date:
            params["date"] = date

        response = requests.get(
            "https://api.nasa.gov/planetary/apod",
            params=params
        )

        if response.status_code != 200:
            logger.error(f"NASA API error: {response.text}")
            raise RuntimeError("Failed to retrieve NASA APOD.")

        data = response.json()

        if data.get("media_type") != "image":
            raise RuntimeError("APOD is not an image today.")

        image_url = data.get("hdurl") or data.get("url")

        try:
            img_data = requests.get(image_url)
            image = Image.open(BytesIO(img_data.content))
        except Exception as e:
            logger.error(f"Failed to load APOD image: {str(e)}")
            raise RuntimeError("Failed to load APOD image.")

        # Adapter l'image a la resolution du device sans distorsion
        target_w, target_h = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            target_w, target_h = target_h, target_w  # inverse

        # Rotation si necessaire : image paysage sur ecran portrait ou inversement
        img_w, img_h = image.size
        if (img_w > img_h and target_h > target_w) or (img_h > img_w and target_w > target_h):
              image = image.rotate(-90, expand=True)

        # Redimensionne en conservant le ratio, puis centre dans un cadre
        img_w, img_h = image.size
        scale = max(target_w / img_w, target_h / img_h)
        resized_w, resized_h = int(img_w * scale), int(img_h * scale)
        image = image.resize((resized_w, resized_h), Image.LANCZOS)

        # Recadrage centre la taille exacte du display
        left = (resized_w - target_w) // 2
        top = (resized_h - target_h) // 2
        image = image.crop((left, top, left + target_w, top + target_h))

        return image
