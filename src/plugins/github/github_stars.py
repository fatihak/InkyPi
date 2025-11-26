import logging
import requests

logger = logging.getLogger(__name__)

def stars_generate_image(plugin_instance, settings, device_config):
    username = settings.get('githubUsername')
    repository = settings.get('githubRepository')

    dimensions = device_config.get_resolution()
    if device_config.get_config("orientation") == "vertical":
        dimensions = dimensions[::-1]

    github_repository = username + "/" + repository
    if not github_repository:
        raise RuntimeError("GitHub repository is required.")

    try:
        stars = fetch_stars(github_repository)
    except Exception as e:
        logger.error(f"GitHub graphql request failed: {str(e)}")
        raise RuntimeError(f"GitHub request failure, please check logs")

    template_params = {
        "repository": github_repository,
        "stars": stars,
        "plugin_settings": settings
    }

    return plugin_instance.render_image(
        dimensions,
        "github_stars.html",
        "github.css",
        template_params
    )

def fetch_stars(github_repository):
    global data
    url = f"https://api.github.com/repos/{github_repository}"
    headers = {"Accept": "application/json"}

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
    else:
        logger.error(f"GitHub Stars Plugin: Error: {response.status_code} - {response.text}")

    return data['stargazers_count']

