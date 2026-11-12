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
    config.get_config.side_effect = lambda key, default=None: default
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


def test_preview_uploads_do_not_overwrite_saved_images(setup, tmp_path, monkeypatch):
    client, fake, _, _ = setup
    saved = tmp_path / "static" / "images" / "saved"
    saved.mkdir(parents=True)
    (saved / "photo.png").write_bytes(b"used by a playlist item")
    from utils import app_utils
    monkeypatch.setattr(app_utils, "resolve_path", lambda rel: str(tmp_path / rel))
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "blue").save(buf, "PNG")
    buf.seek(0)
    response = client.post("/preview_image", content_type="multipart/form-data",
                           data={"plugin_id": "demo", "imageFiles[]": (buf, "photo.png")})
    assert response.status_code == 200
    preview_path = fake.calls[-1]["imageFiles[]"][0]
    assert not preview_path.startswith(str(saved))
    assert not os.path.exists(preview_path)                     # temporary copy removed
    assert (saved / "photo.png").read_bytes() == b"used by a playlist item"


def test_show_on_display_sends_the_previewed_image(setup):
    client, fake, _, display = setup
    refresh_task = mock.Mock(running=True)
    client.application.config["REFRESH_TASK"] = refresh_task
    response = client.post("/preview_image", data={"plugin_id": "demo"})
    preview_id = response.headers["X-Preview-Id"]

    response = client.post("/display_preview", json={"preview_id": preview_id})
    assert response.status_code == 200
    action = refresh_task.manual_update.call_args[0][0]
    assert action.get_plugin_id() == "demo"
    assert action.execute(None, None, None).getpixel((0, 0)) == (255, 0, 0)
    assert len(fake.calls) == 1                                   # not rendered again

    assert client.post("/display_preview", json={"preview_id": "other"}).status_code == 410
