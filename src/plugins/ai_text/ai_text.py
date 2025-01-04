import urllib.request
from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import resolve_path, get_font
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import requests
import logging
import textwrap

logger = logging.getLogger(__name__)

IMAGE_MODELS = ["dall-e-3", "dall-e-2"]
DEFAULT_IMAGE_MODEL = "dall-e-3"

IMAGE_QUALITIES = ["hd", "standard"]
DEFAULT_IMAGE_QUALITY = "standard"
class AIText(BasePlugin):
    def generate_image(self, settings, device_config):

        api_key = device_config.load_env_key("OPEN_AI_SECRET")
        if not api_key:
            raise RuntimeError("OPEN AI API Key not configured.")

        title = settings.get("title")

        text_model = settings.get('textModel')
        if not text_model or text_model not in ['gpt-4o', 'gpt-4o-mini']:
            raise RuntimeError("Text Model is required.")

        text_prompt = settings.get('inputText', '')
        if not text_model.strip():
            raise RuntimeError("Text Prompt is required.")

        try:
            ai_client = OpenAI(api_key = api_key)
            prompt_response = AIText.fetch_text_prompt(ai_client, text_model, text_prompt)
        except Exception as e:
            logger.error(f"Failed to make Open AI request: {str(e)}")
            raise RuntimeError("Open AI request failure, please check logs.")
        
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        
        image = AIText.generate_text_image(dimensions, title, prompt_response)

        return image
    
    @staticmethod
    def fetch_text_prompt(ai_client, model, text_prompt):
        logger.info(f"Getting random image prompt...")

        system_content = (
            "You are a highly intelligent text generation assistant. Generate concise, "
            "relevant, and accurate responses tailored to the user's input. Adapt your "
            "tone and content to align with the context of the user's request. Don't repeat "
            "the prompt back to the user or rephrase it, just provide the response itself. "
        )
        user_content = text_prompt

        # Make the API call
        response = ai_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            temperature=1,  # Adjust for creativity
            max_tokens=300
        )

        prompt = response.choices[0].message.content.strip()
        logger.info(f"Generated random image prompt: {prompt}")
        return prompt

    @staticmethod
    def generate_text_image(dimensions, title, body):
        w,h = dimensions
        background_color = (255,255,255)
        text_color = (0,0,0)
        image = Image.new("RGBA", dimensions, background_color+(255,))
        image_draw = ImageDraw.Draw(image)

        # Adaptive font size based on image dimensions
        font_size = max(10, min(w, h) // 20)
        font = get_font("jost", font_size)

        # Maximum text width in pixels
        max_text_width = w - 30

        # Dynamic line height based on font size
        line_height = font_size + 5

        # Word-wrap text using pixel-based constraints
        words = body.split()
        wrapped_lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            test_width = image_draw.textlength(test_line, font=font)
            if test_width <= max_text_width:
                current_line.append(word)
            else:
                wrapped_lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            wrapped_lines.append(' '.join(current_line))

        # Calculate the starting y-coordinate to center the text vertically
        total_text_height = len(wrapped_lines) * line_height

        title_height = max(h // 30, 0) if title else 0
        y = max((h - total_text_height - title_height) // 2, 0)
        x = w/2  # Left padding

        if title:
            title_font_size = max(10, min(w, h) // 15)
            fnt = get_font("jost-semibold", title_font_size)

            image_draw.text((x, y), title, anchor="mb", fill=text_color, font=fnt)
            y += title_height


        # Draw the wrapped text line by line
        for line in wrapped_lines:
            image_draw.text((x, y), line, font=font, anchor="mm", fill=text_color)
            y += line_height
        return image
