from plugins.base_plugin.base_plugin import BasePlugin
from datetime import datetime, timedelta
import requests
import logging
from pytz import timezone, utc

logger = logging.getLogger(__name__)


class NHLTeamSchedule(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params["style_settings"] = "enabled"
        return template_params

    def generate_image(self, settings, device_config):
        nhl_team = settings.get("nhlTeam")
        if not nhl_team:
            raise RuntimeError("NHL Team is required.")
        
        todays_game, next_game = self.get_game_schedule(nhl_team)
        day, time, selected_game = self.get_day_and_time(todays_game, next_game)
        networks = self.get_game_story(selected_game["id"])
        home_team = selected_game["homeTeam"]
        away_team = selected_game["awayTeam"]

        home_team_stats, away_team_stats = self.get_team_stats(home_team, away_team)

        # Get design choice from settings, default to original
        design_choice = settings.get("design", "original")
        
        # Map design choices to template files
        design_templates = {
            "original": ("nhl_team_schedule.html", "nhl_team_schedule.css"),
            "enhanced": ("designs/enhanced_layout.html", "designs/enhanced_layout.css"),
            "stats_focused": ("designs/stats_focused.html", "designs/stats_focused.css"),
            "card_style": ("designs/card_style.html", "designs/card_style.css"),
            "minimalist": ("designs/minimalist.html", "designs/minimalist.css"),
            "dashboard": ("designs/dashboard.html", "designs/dashboard.css"),
            "timeline": ("designs/timeline.html", "designs/timeline.css"),
            "bracket": ("designs/bracket.html", "designs/bracket.css")
        }
        
        # Use original if invalid design choice
        html_template, css_template = design_templates.get(design_choice, design_templates["original"])

        image_template_params = {
            "day": day,
            "time": time,
            "home_team": home_team,
            "away_team": away_team,
            "networks": networks,
            "plugin_settings": settings,
            "title": f"{home_team.get('commonName', {}).get('default', '')} vs {away_team.get('commonName', {}).get('default', '')}",
            "home_team_stats": home_team_stats,
            "away_team_stats": away_team_stats,
        }

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        image = self.render_image(
            dimensions,
            html_template,
            css_template,
            image_template_params,
        )

        return image
    
    def get_game_schedule(self, nhl_team):
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
            raise RuntimeError("Failed to fetch NHL team schedule data.")

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
        
        return todays_game, next_game
    
    def get_game_story(self, game_id):
        # contains some pre-game statistics like PK percentage etc
        response = requests.get(
            f"https://api-web.nhle.com/v1/wsc/game-story/{game_id}",
            timeout=10,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 200:
            data = response.json()
        else:
            logger.error(
                f"NHL Team Schedule Plugin: Error: {response.status_code} - {response.text}"
            )
            raise RuntimeError("Failed to fetch game story data.")
        
        networks = []

        for tv_broadcast in data.get("tvBroadcasts", []):
            networks.append(tv_broadcast["network"])

        return networks
    
    def get_team_stats(self, home_team, away_team):
        response = requests.get(
            "https://api-web.nhle.com/v1/standings/now",
            timeout=10,
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 200:
            data = response.json()
        else:
            logger.error(
                f"NHL Team Schedule Plugin: Error: {response.status_code} - {response.text}"
            )
            raise RuntimeError("Failed to fetch team stats data.")
        
        home_team_stats = {}
        away_team_stats = {}
        for team in data.get("standings", []):
            if team["teamCommonName"]["default"] == home_team["commonName"]["default"]:
                home_team_stats = team
            elif team["teamCommonName"]["default"] == away_team["commonName"]["default"]:
                away_team_stats = team
            elif home_team_stats and away_team_stats:
                break

        return home_team_stats, away_team_stats
    
    def get_day_and_time(self, todays_game, next_game):
        eastern = timezone('US/Eastern')
        utc_dt = datetime.strptime(todays_game['startTimeUTC'] if todays_game else next_game['startTimeUTC'], "%Y-%m-%dT%H:%M:%SZ")
        eastern_dt = utc.localize(utc_dt).astimezone(eastern)
        time = eastern_dt.strftime('%H:%M %Z')

        if todays_game:
            day = "Today"
            selected_game = todays_game
        elif next_game:
            day = "Tomorrow" if next_game['gameDate'] == (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d") else eastern_dt.strftime('%A, %B %d')
            selected_game = next_game
        else:
            raise RuntimeError("No upcoming games found.")

        return day, time, selected_game
