import base64
from io import BytesIO
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from src.plugins.ai_image.ai_image import AIImage


def png_b64():
    buffer = BytesIO()
    Image.new("RGB", (4, 4)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def generate(settings):
    client = Mock()
    client.images.generate.return_value = Mock(data=[Mock(b64_json=png_b64())])
    device_config = Mock()
    device_config.load_env_key.return_value = "test-key"
    device_config.get_config.return_value = "horizontal"

    with patch("src.plugins.ai_image.ai_image.OpenAI", return_value=client):
        AIImage({"id": "ai_image"}).generate_image(settings, device_config)

    return client.images.generate.call_args.kwargs["model"]


@pytest.mark.parametrize(
    "settings",
    [
        {"textPrompt": "a lighthouse"},
        # instances saved before gpt-image-1 was retired
        {"textPrompt": "a lighthouse", "imageModel": "gpt-image-1"},
    ],
)
def test_uses_gpt_image_2_instead_of_retired_gpt_image_1(settings):
    assert generate(settings) == "gpt-image-2"


def test_keeps_selected_gpt_image_2():
    assert generate({"textPrompt": "a lighthouse", "imageModel": "gpt-image-2"}) == "gpt-image-2"


def test_rejects_unknown_model():
    with pytest.raises(RuntimeError, match="Invalid Image Model"):
        generate({"textPrompt": "a lighthouse", "imageModel": "dall-e-3"})
