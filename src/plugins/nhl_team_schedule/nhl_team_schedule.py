from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import resolve_path
from PIL import Image, ImageDraw, ImageFont
from utils.image_utils import resize_image
from io import BytesIO
from datetime import datetime
import requests
import logging
import textwrap
import os

logger = logging.getLogger(__name__)


class NHLTeamSchedule(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params["style_settings"] = True
        return template_params

    def generate_image(self, settings, device_config):
        title = settings.get("title")

        nhl_team = settings.get("nhlTeam")
        if not nhl_team:
            raise RuntimeError("NHL Team is required.")

        response = requests.get(
            f"https://api-web.nhle.com/v1/club-schedule-season/{nhl_team}/now",
            timeout=10,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 200:
            data = response.json()
        else:
            logger.error(
                f"NHL Team Schedule Plugin: Error: {response.status_code} - {response.text}"
            )

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        image_template_params = {
            "title": title,
            "home_team": data["games"][0]["homeTeam"],
            "away_team": data["games"][0]["awayTeam"],
            "plugin_settings": settings,
        }

        image = self.render_image(
            dimensions,
            "nhl_team_schedule.html",
            "nhl_team_schedule.css",
            image_template_params,
        )

        return image
