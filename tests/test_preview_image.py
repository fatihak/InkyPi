import io
import os
import sys
from unittest import mock

import pytest
from flask import Flask
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from blueprints import plugin as plugin_module  # noqa: E402


class FakePlugin:
    def __init__(self):
        self.calls = []

    def generate_image(self, settings, device_config):
        self.calls.append(dict(settings))
        if settings.get("fail"):
            raise RuntimeError("cannot render")
        return Image.new("RGB", (80, 48), "red")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    upload_dir = tmp_path / "saved"
    fake = FakePlugin()
    monkeypatch.setattr(plugin_module, "get_plugin_instance", lambda cfg: fake)
    app = Flask(__name__)
    app.register_blueprint(plugin_module.plugin_bp)
    config = mock.Mock()
    config.get_plugin.side_effect = lambda pid: {"id": pid} if pid == "demo" else None
    app.config["DEVICE_CONFIG"] = config
    display = mock.Mock()
    app.config["DISPLAY_MANAGER"] = display
    return app.test_client(), fake, upload_dir, display


def test_preview_returns_png_without_touching_display(setup):
    client, fake, _, display = setup
    response = client.post("/preview_image", data={"plugin_id": "demo", "title": "unsaved"})
    assert response.status_code == 200 and response.mimetype == "image/png"
    assert Image.open(io.BytesIO(response.data)).size == (80, 48)
    assert fake.calls == [{"title": "unsaved"}]
    display.display_image.assert_not_called()


def test_preview_errors(setup):
    client = setup[0]
    assert client.post("/preview_image", data={"plugin_id": "nope"}).status_code == 404
    response = client.post("/preview_image", data={"plugin_id": "demo", "fail": "1"})
    assert response.status_code == 500 and "cannot render" in response.get_json()["error"]


def test_only_one_preview_at_a_time(setup):
    client = setup[0]
    assert plugin_module._preview_lock.acquire(blocking=False)
    try:
        assert client.post("/preview_image", data={"plugin_id": "demo"}).status_code == 429
    finally:
        plugin_module._preview_lock.release()


def test_preview_can_simulate_the_display(setup):
    from utils import eink
    client, fake, _, display = setup
    display.get_palette.return_value = eink.SPECTRA6
    app_config = client.application.config["DEVICE_CONFIG"]
    app_config.get_config.return_value = {}
    response = client.post("/preview_image", data={"plugin_id": "demo", "simulateDisplay": "true",
                                                   "colourMode": "graphics"})
    assert response.status_code == 200
    image = Image.open(io.BytesIO(response.data)).convert("RGB")
    # pure red is shown as the measured red ink, not as (255, 0, 0)
    assert image.getpixel((10, 10)) != (255, 0, 0)
    assert "simulateDisplay" not in fake.calls[-1]
    display.display_image.assert_not_called()


def test_colour_only_changes_reuse_the_last_plugin_render(setup):
    from utils import eink
    client, fake, _, display = setup
    display.get_palette.return_value = eink.SPECTRA6
    client.application.config["DEVICE_CONFIG"].get_config.return_value = {}
    plugin_module._preview_cache.clear()
    base = {"plugin_id": "demo", "title": "x", "colourMode": "graphics"}

    first = client.post("/preview_image", data={**base, "reuseRender": "true"})
    assert first.headers["X-Preview-Reused"] == "0" and len(fake.calls) == 1
    # simulation and colour mode changes: same plugin image, only re-rendered colours
    again = client.post("/preview_image", data={**base, "colourMode": "photo", "simulateDisplay": "true",
                                                 "reuseRender": "true"})
    assert again.status_code == 200 and again.headers["X-Preview-Reused"] == "1" and len(fake.calls) == 1
    # without reuseRender (Preview / Render again buttons), or with other settings: rendered again
    client.post("/preview_image", data=base)
    client.post("/preview_image", data={**base, "title": "y", "reuseRender": "true"})
    assert len(fake.calls) == 3
    assert "reuseRender" not in fake.calls[-1]
