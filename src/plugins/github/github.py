from ..base_plugin.base_plugin import BasePlugin
from .github_contributions import contributions_generate_image
from .github_sponsors import sponsors_generate_image
import logging

logger = logging.getLogger(__name__)

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
        try:
            return contributions_generate_image(self, settings, device_config)
        except Exception as e:
            logger.error(f"GitHub image generation failed: {str(e)}")
            raise