from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
from io import BytesIO
import requests
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)
GRAPHQL_QUERY = """
query($username: String!) {
  user(login: $username) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
          }
        }
      }
    }
  }
}
"""

class GitHub(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "GitHub",
            "expected_key": "GITHUB_SECRET"
        }
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        api_key = device_config.load_env_key("GITHUB_SECRET")
        if not api_key:
            raise RuntimeError("GitHub API Key not configured.")

        colors = settings.get("contributionColor[]")
        github_username = settings.get("githubUsername")
        if not github_username:
            raise RuntimeError("GitHub username is required.")

        try:
            data = self.fetch_contributions(github_username, api_key)
        except Exception as e:
            logger.error(f"GitHub graphql request failed: {str(e)}")
            raise RuntimeError(f"GitHub request failure, please check logs")

        grid, month_positions = self.parse_contributions(data, colors)
        metrics = self.calculate_metrics(data)

        template_params = {
            "username": github_username,
            "grid": grid,
            "month_positions": month_positions,
            "metrics": metrics,
            "plugin_settings": settings
        }

        image = self.render_image(dimensions, "github.html", "github.css", template_params)
        return image
    
    def fetch_contributions(self, username, api_key):
        url = "https://api.github.com/graphql"
        headers = {"Authorization": f"Bearer {api_key}"}
        variables = {"username": username}

        resp = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": variables}, headers=headers)
        resp.raise_for_status()

        return resp.json()
    
    def parse_contributions(self, data, colors):
        weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]

        # Flatten into grid: weeks -> days
        grid = [[day for day in week["contributionDays"]] for week in weeks]

        max_contrib = max(day["contributionCount"] for week in grid for day in week)
        def get_color(count):
            if max_contrib == 0 or count == 0:
                return colors[0]
            # Scale into 1–4 range for counts > 0
            level = int((count / max_contrib) * (len(colors) - 1))
            return colors[max(1,level)]
        # add color to each day
        for week in grid:
            for day in week:
                day["color"] = get_color(day["contributionCount"])

        # Precompute month positions
        month_positions = []
        seen_months = set()
        for i, week in enumerate(weeks):
            first_day = week["contributionDays"][0]["date"]
            dt = datetime.strptime(first_day, "%Y-%m-%d")
            month_year = f"{dt.strftime('%b')}-{dt.year}"  # e.g., "Aug-2025"

            if month_year not in seen_months:
                month_positions.append({"name": dt.strftime("%b"), "index": i})
                seen_months.add(month_year)
        month_positions.pop(0)
        return grid, month_positions
    
    def calculate_metrics(self, data):
        weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        days = [day for week in weeks for day in week["contributionDays"]]
        days = sorted(days, key=lambda d: d["date"])

        total = sum(day["contributionCount"] for day in days)

        streak, longest_streak, current_streak = 0, 0, 0
        today = date.today()
        yesterday = today - timedelta(days=1)
        in_current_streak = False

        for day in days:
            day_date = date.fromisoformat(day["date"])
            if day["contributionCount"] > 0:
                streak += 1
                if streak > longest_streak:
                    longest_streak = streak
                # Track current streak if it's today or yesterday
                if day_date == today or day_date == yesterday or in_current_streak:
                    current_streak = streak
                    in_current_streak = True
            else:
                streak = 0
                in_current_streak = False
        
        return [
            {"title": "Contributions", "value": total},
            {"title": "Current Streak", "value": current_streak},
            {"title": "Longest Streak", "value": longest_streak},
        ] 