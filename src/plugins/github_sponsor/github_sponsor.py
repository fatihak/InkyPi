from plugins.base_plugin.base_plugin import BasePlugin
import requests
import logging

logger = logging.getLogger(__name__)
GRAPHQL_QUERY = """
query($username: String!) {
  user(login: $username) {
    sponsorshipsAsMaintainer(first: 100) {
      totalCount
      nodes {
        createdAt
        sponsorEntity {
          ... on User {
            login
            name
          }
          ... on Organization {
            login
            name
          }
        }
        tier {
          name
          monthlyPriceInCents
        }
      }
    }
    estimatedNextSponsorsPayoutInCents
  }
}
"""

class GitHubSponsor(BasePlugin):
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

        github_username = settings.get("githubUsername")
        if not github_username:
            raise RuntimeError("GitHub username is required.")

        try:
            data = self.fetch_contributions(github_username, api_key)
        except Exception as e:
            logger.error(f"GitHub graphql request failed: {str(e)}")
            raise RuntimeError(f"GitHub request failure, please check logs")

        total_per_month = self.get_total_for_month(data)

        template_params = {
            "username": github_username,
            "total_per_month": total_per_month,
            "plugin_settings": settings
        }

        image = self.render_image(dimensions, "github.html", "github.css", template_params)
        return image

    def get_total_for_month(self, data) -> int:
        sponsorships = data['data']['user']['sponsorshipsAsMaintainer']['nodes']
        total_per_month = 0
        for s in sponsorships:
            monthly_cents = s['tier']['monthlyPriceInCents']
            monthly_dollars = monthly_cents / 100

            total_per_month += monthly_dollars
        return int(total_per_month)

    def fetch_contributions(self, username, api_key):
        url = "https://api.github.com/graphql"
        headers = {"Authorization": f"Bearer {api_key}"}
        variables = {"username": username}

        resp = requests.post(url, json={"query": GRAPHQL_QUERY, "variables": variables}, headers=headers)
        resp.raise_for_status()

        print(resp.json())

        return resp.json()
