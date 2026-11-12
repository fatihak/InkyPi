"""Minimal translation support for the web interface.

Catalogs live in src/translations/<lang>.json and map the English source text
to its translation. A missing entry falls back to English, so a partial
catalog never breaks a page. Placeholders use str.format: "Every {n} min".
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"
UI_LANGUAGES = {"en": "English", "fr": "Français"}
TRANSLATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "translations")

_catalogs = {}


def get_catalog(language):
    """Returns the {english: translation} catalog of a language ({} for English or unknown)."""
    if language not in UI_LANGUAGES or language == DEFAULT_LANGUAGE:
        return {}
    if language not in _catalogs:
        path = os.path.join(TRANSLATIONS_DIR, f"{language}.json")
        try:
            with open(path, encoding="utf-8") as f:
                _catalogs[language] = json.load(f)
        except (OSError, ValueError) as e:
            logger.error(f"Could not load translations for '{language}': {e}")
            _catalogs[language] = {}
    return _catalogs[language]


def translate(text, language=DEFAULT_LANGUAGE, **kwargs):
    """Translates text (English source) and fills {placeholders} from kwargs."""
    translated = get_catalog(language).get(text, text)
    if kwargs:
        try:
            return translated.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text.format(**kwargs)
    return translated


def normalize_language(language):
    return language if language in UI_LANGUAGES else DEFAULT_LANGUAGE


def current_language():
    """UI language of the device (Settings > Interface language), inside a request."""
    try:
        from flask import current_app
        config = current_app.config["DEVICE_CONFIG"]
        return normalize_language(config.get_config("ui_language", default=DEFAULT_LANGUAGE))
    except (RuntimeError, KeyError):
        return DEFAULT_LANGUAGE


def _(text, **kwargs):
    """Translate into the device's UI language (for blueprints and template filters)."""
    return translate(text, current_language(), **kwargs)
