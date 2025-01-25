import urllib.request
from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import resolve_path, get_font
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from utils.image_utils import resize_image
from io import BytesIO
from datetime import datetime
import requests
import logging
import textwrap
import os

logger = logging.getLogger(__name__)

FRAME_STYLES = [
    {
        "name": "None",
        "icon": "frames/blank.png"
    },
    {
        "name": "Corner",
        "icon": "frames/corner.png"
    },
    {
        "name": "Top and Bottom",
        "icon": "frames/top_and_bottom.png"
    },
    {
        "name": "Rectangle",
        "icon": "frames/rectangle.png"
    }
]

class AIText(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['frame_styles'] = FRAME_STYLES
        return template_params

    def generate_image(self, settings, device_config):
        api_key = device_config.load_env_key("OPEN_AI_SECRET")
        if not api_key:
            raise RuntimeError("OPEN AI API Key not configured.")

        title = settings.get("title")

        text_model = settings.get('textModel')
        if not text_model or text_model not in ['gpt-4o', 'gpt-4o-mini']:
            raise RuntimeError("Text Model is required.")
        
        frame = settings.get('selectedFrame')
        if not frame or frame not in [frame['name'] for frame in FRAME_STYLES]:
            frame = "None"

        text_prompt = settings.get('inputText', '')
        if not text_model.strip():
            raise RuntimeError("Text Prompt is required.")

        try:
            ai_client = OpenAI(api_key = api_key)
            prompt_response = AIText.fetch_text_prompt(ai_client, text_model, text_prompt)
        except Exception as e:
            logger.error(f"Failed to make Open AI request: {str(e)}")
            raise RuntimeError("Open AI request failure, please check logs.")

        background_color = settings.get('backgroundColor', "white")
        background_image = settings.get('backgroundImageFile')
        text_color = settings.get('textColor', "black")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        
        try:
            if background_image:
                image = Image.open(background_image)
                image = resize_image(image, dimensions)
            else:
                image = Image.new("RGBA", dimensions, background_color)

            if frame:
                image = AIText.draw_frame(frame, image, text_color)

            image = AIText.generate_text_image(image, dimensions, title, prompt_response, text_color)
        except Exception as e:
            logger.error(f"Failed to generate ai text image: {str(e)}")
            raise RuntimeError("Failed to generate image, please check logs.")
        return image
    
    @staticmethod
    def fetch_text_prompt(ai_client, model, text_prompt):
        logger.info(f"Getting random text prompt from input {text_prompt}")

        system_content = (
            "You are a highly intelligent text generation assistant. Generate concise, "
            "relevant, and accurate responses tailored to the user's input. The response "
            "should be 70 words or less."
            "IMPORTANT: Do not rephrase, reword, or provide an introduction. Respond directly "
            "to the request without adding explanations or extra context "
            "IMPORTANT: If the response naturally requires a newline for formatting, provide "
            "the '\n' newline character explicitly for every new line. For regular sentences "
            "or paragraphs do not provide the new line character."
            f"For context, today is {datetime.today().strftime('%Y-%m-%d')}"
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
            temperature=1
        )

        prompt = response.choices[0].message.content.strip()
        logger.info(f"Generated random text prompt: {prompt}")
        return prompt

    @staticmethod
    def generate_text_image(base_image, dimensions, title, body, color=(0,0,0)):
        w,h = dimensions
        dim = min(w,h)
        image_draw = ImageDraw.Draw(base_image)

        # Adaptive font size based on image dimensions
        font_size = max(10, min(w, h) // 20)
        font = get_font("jost", font_size)
        line_height = AIText.get_text_height(font, body) + 4

        title_font_size = max(10, min(w, h) // 18)
        title_font = get_font("jost-semibold", title_font_size)
        title_height = AIText.get_text_height(title_font, title)

        # Maximum text width in pixels
        text_padding = max(dim*0.08, 1)
        max_text_width = w - (text_padding*2)

        wrapped_lines = AIText.wrap_lines(body, image_draw, font, max_text_width)

        total_text_height = len(wrapped_lines) * line_height

        title_height = title_height if title else 0
        y = max((h - total_text_height - title_height) // 2, 0)
        x = w/2

        if title:
            image_draw.text((x, y), title, anchor="mm", fill=color, font=title_font)
            y += title_height

        for line in wrapped_lines:
            image_draw.text((x, y), line, font=font, anchor="mt", fill=color)
            y += line_height
        return base_image

    @staticmethod
    def draw_frame(frame, image, color):
        w,h = image.size
        dim = min(w,h)
        image_draw = ImageDraw.Draw(image)
        width = max(int(dim*0.015), 1)
        padding = max(dim*0.05, 1)

        if frame == "Corner":
            corner_length = max(dim*0.16, 1)
            image_draw.line([ (padding+corner_length, padding), (padding, padding), (padding, padding+corner_length)], fill=color, width = width, joint="curve")
            image_draw.line([ (w-padding-corner_length, h-padding), (w-padding, h-padding), (w-padding, h-padding-corner_length)], fill=color, width = width, joint="curve")
        elif frame == "Top and Bottom":
            image_draw.line([ (padding, 2*padding), (w-padding, 2*padding)], fill=color, width=width)
            image_draw.line([ (padding, h-(2*padding)), (w-padding, h-(2*padding))], fill=color, width=width)
        elif frame == "Rectangle":
            shape = [(padding,padding),(w-padding, h-padding)]
            image_draw.rectangle(shape, outline=color, width=width) 

        return image

    @staticmethod
    def wrap_lines(body, image_draw, font, max_text_width):        
        # Word-wrap text using pixel-based constraints
        words = body.replace("\n", " \n").split(" ")
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
    
    @staticmethod
    def get_text_height(font, text):        
        # Word-wrap text using pixel-based constraints
        left, top, right, bottom = font.getbbox(text)
        return bottom - top

