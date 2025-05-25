from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import resolve_path
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

class AIText(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "OpenAI",
            "expected_key": "OPEN_AI_SECRET"
        }
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        api_key = device_config.load_env_key("OPEN_AI_SECRET")
        if not api_key:
            raise RuntimeError("OPEN AI API Key not configured.")

        title = settings.get("title")

        text_model = settings.get('textModel')
        if not text_model or text_model not in ['gpt-4o', 'gpt-4o-mini']:
            raise RuntimeError("Text Model is required.")

        text_prompt = settings.get('textPrompt', '')
        if not text_prompt.strip():
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

        image_template_params = {
            "title": title,
            "content": prompt_response,
            "plugin_settings": settings
        }
        
        image = self.render_image(dimensions, "ai_text.html", "ai_text.css", image_template_params)

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