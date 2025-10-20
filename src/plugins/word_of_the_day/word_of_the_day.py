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


class WordOfTheDay(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params["api_key"] = {
            "required": True,
            "service": "OpenAI",
            "expected_key": "OPEN_AI_SECRET",
        }
        template_params["style_settings"] = True
        return template_params

    def generate_image(self, settings, device_config):
        api_key = device_config.load_env_key("OPEN_AI_SECRET")
        if not api_key:
            raise RuntimeError("OPEN AI API Key not configured.")

        text_lang = settings.get("wordLang")
        if not text_lang:
            raise RuntimeError("Text lang is required.")

        text_model = settings.get("textModel")
        if not text_model:
            raise RuntimeError("Text Model is required.")

        try:
            ai_client = OpenAI(api_key=api_key)
            prompt_response = self.fetch_text_prompt(ai_client, text_model, text_lang)
        except Exception as e:
            logger.error(f"Failed to make Open AI request: {str(e)}")
            raise RuntimeError("Open AI request failure, please check logs.")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        image_template_params = {
            "content": prompt_response,
            "plugin_settings": settings,
        }

        image = self.render_image(
            dimensions, "ai_text.html", "ai_text.css", image_template_params
        )

        return image

    @staticmethod
    def fetch_text_prompt(ai_client, model, text_lang):
        logger.info(
            f"Getting random text prompt from in {text_lang}, model: {model}"
        )

        system_content = (
            "You are an assistant that gives a word of the day in JSON format."
        )
        user_content = f"Give me the word of the day in {text_lang} with fields: word, type, description, and example."

        # Make the API call
        response = ai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            temperature=1,
        )

        prompt = response.choices[0].message.content
        logger.info(f"Generated random text prompt: {prompt}")
        return prompt
