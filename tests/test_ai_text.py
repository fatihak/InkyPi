from unittest.mock import Mock, patch

import pytest

from src.plugins.ai_text.ai_text import AIText


def generate(settings):
    client = Mock()
    client.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content="Hello"))]
    )
    device_config = Mock()
    device_config.load_env_key.return_value = "test-key"
    device_config.get_resolution.return_value = (800, 480)
    device_config.get_config.return_value = "horizontal"

    plugin = AIText({"id": "ai_text"})
    with patch("src.plugins.ai_text.ai_text.OpenAI", return_value=client), \
            patch.object(plugin, "render_image"):
        plugin.generate_image(settings, device_config)

    return client.chat.completions.create.call_args.kwargs["model"]


def test_uses_gpt_5_6_luna_instead_of_retired_gpt_4_1_nano():
    # instances saved before gpt-4.1-nano was retired
    assert generate({"textModel": "gpt-4.1-nano", "textPrompt": "a haiku"}) == "gpt-5.6-luna"


@pytest.mark.parametrize("model", ["gpt-4o-mini", "gpt-5-nano", "gpt-5.6-luna"])
def test_keeps_selected_model(model):
    assert generate({"textModel": model, "textPrompt": "a haiku"}) == model
