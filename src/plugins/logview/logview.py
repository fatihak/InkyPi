import os
from utils.app_utils import resolve_path, get_font
from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageColor, ImageDraw, ImageFont
from io import BytesIO
import logging
import numpy as np
import math
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

class LogView(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        return template_params
