from io import BytesIO
from unittest.mock import Mock, patch

import pytest
import requests
from PIL import Image

from src.utils.image_loader import AdaptiveImageLoader


class FakeResponse:
    def __init__(self, content, error=None):
        self.raw = BytesIO(content)
        self.content = content
        self.error = error
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True
        self.raw.close()

    def raise_for_status(self):
        if self.error:
            raise self.error

    def iter_content(self, chunk_size):
        yield self.content


@pytest.mark.parametrize("low_resource", [False, True])
@pytest.mark.parametrize("outcome", ["success", "http_error", "invalid_image"])
def test_streamed_image_response_is_closed(low_resource, outcome):
    data = BytesIO()
    Image.new("RGB", (8, 6), "red").save(data, format="PNG")
    response = FakeResponse(
        b"not an image" if outcome == "invalid_image" else data.getvalue(),
        requests.HTTPError("download failed") if outcome == "http_error" else None,
    )
    session = Mock()
    session.get.return_value = response
    loader = AdaptiveImageLoader.__new__(AdaptiveImageLoader)
    loader.is_low_resource = low_resource

    with patch("src.utils.image_loader.get_http_session", return_value=session):
        image = loader.from_url("https://example.com/image.png", (4, 3))

    assert response.closed
    if outcome == "success":
        assert image.size == (4, 3)
        assert image.getpixel((0, 0)) == (255, 0, 0)
    else:
        assert image is None
