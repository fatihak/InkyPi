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

IMAGE_TEMPLATES = [
    {
        "name": "Simple",
        "icon": "templates/simple_template.png"
    }
]

class AIText(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['image_templates'] = CLOCK_FACES
        return template_params

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

        #return "Why can't a nose be 12 inches long? Because then it would be a foot!"
        system_content = (
            "You are a highly intelligent text generation assistant. Generate concise, "
            "relevant, and accurate responses tailored to the user's input. The response "
            "should be 70 words or less."
            "IMPORTANT: Do not rephrase, reword, or provide an introduction. Respond directly "
            "to the request without adding explanations or extra context "
            "IMPORTANT: If the response naturally requires a newline for formatting, provide "
            "the '\n' newline character explicitly for every new line. For regular sentences "
            "or paragraphs do not provide the new line character."
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
    def generate_text_image(dimensions, title, body, primary_color=(0,0,0), secondary_color = (255,255,255)):
        w,h = dimensions
        dim = min(w,h)
        text_color = (0,0,0)
        image = Image.new("RGBA", dimensions, secondary_color+(255,))
        image_draw = ImageDraw.Draw(image)

        # draw corner style
        width = max(int(dim*0.015), 1)
        padding = max(dim*0.06, 1)
        corner_length = max(dim*0.16, 1)
        image_draw.line([ (padding+corner_length, padding), (padding, padding), (padding, padding+corner_length)], fill=primary_color, width = width, joint="curve")
        image_draw.line([ (w-padding-corner_length, h-padding), (w-padding, h-padding), (w-padding, h-padding-corner_length)], fill=primary_color, width = width, joint="curve")

        # Adaptive font size based on image dimensions
        font_size = max(10, min(w, h) // 20)
        font = get_font("jost", font_size)

        # Maximum text width in pixels
        max_text_width = w - (padding*2)

        # Dynamic line height based on font size
        line_height = font_size + 5

        wrapped_lines = AIText.wrap_lines(body, image_draw, font, max_text_width)

        # Calculate the starting y-coordinate to center the text vertically
        total_text_height = len(wrapped_lines) * line_height

        title_height = max(h // 10, 0) if title else 0
        y = max((h - total_text_height - title_height) // 2, 0)
        x = w/2  # Left padding

        if title:
            title_font_size = max(10, min(w, h) // 15)
            fnt = get_font("jost-semibold", title_font_size)

            image_draw.text((x, y), title, anchor="mb", fill=primary_color, font=fnt)
            y += title_height

        # Draw the wrapped text line by line
        for line in wrapped_lines:
            image_draw.text((x, y), line, font=font, anchor="mm", fill=primary_color)
            y += line_height
        return image

    @staticmethod
    def wrap_lines(body, image_draw, font, max_text_width):        
        # Word-wrap text using pixel-based constraints
        words = body.split(" ")
        wrapped_lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            test_width = image_draw.textlength(test_line.replace("\n", ""), font=font)
            if test_width <= max_text_width and "\n" not in word:
                current_line.append(word)
            else:
                wrapped_lines.append(' '.join(current_line))
                current_line = [word.replace("\n", "")]

        if current_line:
            wrapped_lines.append(' '.join(current_line))
        
        return wrapped_lines
