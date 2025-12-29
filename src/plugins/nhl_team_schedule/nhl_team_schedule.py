from plugins.base_plugin.base_plugin import BasePlugin
from datetime import datetime
import requests
import logging
from pytz import timezone, utc

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

        todays_date = datetime.now().strftime("%Y-%m-%d")
        todays_game = None
        next_game = None

        for game in data.get("games", []):
            game_date = game.get("gameDate")
            if game_date == todays_date:
                todays_game = game
                break
            elif not next_game and game_date > todays_date:
                next_game = game

        if todays_game:
            start_utc = datetime.strptime(todays_game['startTimeUTC'], "%Y-%m-%dT%H:%M:%SZ")
            eastern = timezone('US/Eastern')
            start_eastern = utc.localize(start_utc).astimezone(eastern)
            title = f"Today's Game @ {start_eastern.strftime('%H:%M %Z')}"
            selected_game = todays_game
        elif next_game:
            title = f"Next Game {next_game['gameDate']}"
            selected_game = next_game
        else:
            raise RuntimeError("No upcoming games found.")

        image_template_params = {
            "title": title,
            "home_team": selected_game["homeTeam"],
            "away_team": selected_game["awayTeam"],
            "plugin_settings": settings,
        }

        image = self.render_image(
            dimensions,
            "nhl_team_schedule.html",
            "nhl_team_schedule.css",
            image_template_params,
        )

        return image
