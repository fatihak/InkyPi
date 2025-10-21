import json

import requests
from plugins.base_plugin.base_plugin import BasePlugin
from openai import OpenAI
from datetime import date
import logging

logger = logging.getLogger(__name__)

RANDOM_WORD_URL = "https://random-word-api.vercel.app/api?words=1"

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
            word = self.get_random_word()
            ai_client = OpenAI(api_key=api_key)
            prompt_response = self.fetch_text_prompt(ai_client, text_model, text_lang, word)

        except Exception as e:
            logger.error(f"Failed to make Open AI request: {str(e)}")
            raise RuntimeError("Open AI request failure, please check logs.")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        print(prompt_response)
        image_template_params = {
            "word": prompt_response["word"].capitalize(),
            "type": prompt_response["type"].capitalize(),
            "meaning": prompt_response["meaning"].capitalize(),
            "example": prompt_response["example"].capitalize(),
            "lecture": prompt_response.get("lecture", ""),
            "plugin_settings": settings,
        }

        image = self.render_image(
            dimensions,
            "word_of_the_day.html",
            "word_of_the_day.css",
            image_template_params,
        )

        return image

    @staticmethod
    def get_random_word():
        # Make the API call
        response = requests.get(RANDOM_WORD_URL) 

        logger.info(f"Random word: {response}")
        try:
            word = response.json()
            logger.info(f"Parsed JSON: {word}")
            return word 
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return None

    @staticmethod
    def fetch_text_prompt(ai_client, model, text_lang, word):
        logger.info(f"Getting random text prompt from in {text_lang}, model: {model}")

        system_content = "You are an assistant that returns only valid JSON objects."

        user_content = f"""
        Given the word '{word}', provide its equivalent in {text_lang}.

        Return a valid JSON object with the following fields:
        - word: the translated word in {text_lang}
        - type: part of speech (noun, verb, adjective, etc.)
        - meaning: a concise definition in English
        - example: one clear example sentence showing correct usage (in {text_lang})
        - lecture: include ONLY if the word is not written in the Roman alphabet

        The JSON must be strictly valid and contain no additional text, comments, or formatting.
        """

        # Make the API call
        response = ai_client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            temperature=0.9,
        )

        prompt = response.choices[0].message.content
        logger.info(f"Generated random text prompt: {prompt}")
        try:
            prompt_data = json.loads(prompt)
            logger.info(f"Parsed JSON: {prompt_data}")
            return prompt_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            return None
