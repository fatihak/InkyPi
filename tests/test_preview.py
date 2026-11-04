import base64
import os
import sys
from io import BytesIO

import pytest
from flask import Flask
from PIL import Image

# The blueprint imports its siblings as top-level modules (e.g. `refresh_task`), so
# import it the same way; going through `src.` would create a second RENDER_LOCK.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

import blueprints.plugin as plugin_module  # noqa: E402
from refresh_task import RENDER_LOCK  # noqa: E402


class FakeDeviceConfig:
    def __init__(self, resolution=(800, 480), orientation="horizontal"):
        self.config = {"resolution": list(resolution), "orientation": orientation}
        self.plugins = {"fake": {"id": "fake", "image_settings": []}}

    def get_config(self, key=None, default={}):
        return self.config.get(key, default)

    def get_plugin(self, plugin_id):
        return self.plugins.get(plugin_id)

    def get_resolution(self):
        width, height = self.config["resolution"]
        return (int(width), int(height))


class FakePlugin:
    def __init__(self, image_size=(4000, 3000), image=True):
        self.config = {"image_settings": []}
        self.image_size = image_size
        self.image = image
        self.received_settings = None
        self.lock_held = None

    def generate_image(self, settings, device_config):
        self.received_settings = settings
        self.lock_held = RENDER_LOCK.locked()
        if not self.image:
            return None
        return Image.new("RGB", self.image_size, "white")


@pytest.fixture
def make_client(monkeypatch, tmp_path):
    monkeypatch.setenv("SRC_DIR", str(tmp_path))
    (tmp_path / "static" / "images" / "saved").mkdir(parents=True)

    def _make(plugin=None, device_config=None):
        plugin = plugin or FakePlugin()
        monkeypatch.setattr(plugin_module, "get_plugin_instance", lambda config: plugin)
        app = Flask(__name__)
        app.config["DEVICE_CONFIG"] = device_config or FakeDeviceConfig()
        app.register_blueprint(plugin_module.plugin_bp)
        return app.test_client(), plugin

    return _make


def preview_size(response):
    data = response.get_json()["image"].split(",", 1)[1]
    with Image.open(BytesIO(base64.b64decode(data))) as img:
        return img.size


class TestPreviewValidation:

    def test_missing_plugin_id_returns_400(self, make_client):
        client, _ = make_client()
        response = client.post("/preview", data={})
        assert response.status_code == 400
        assert "plugin_id" in response.get_json()["error"]

    def test_unknown_plugin_returns_404(self, make_client):
        client, _ = make_client()
        response = client.post("/preview", data={"plugin_id": "nope"})
        assert response.status_code == 404

    def test_none_image_returns_500_and_releases_lock(self, make_client):
        client, _ = make_client(plugin=FakePlugin(image=False))
        response = client.post("/preview", data={"plugin_id": "fake"})
        assert response.status_code == 500
        assert "Chromium" in response.get_json()["error"]
        assert not RENDER_LOCK.locked()


class TestPreviewResize:

    def test_scaled_to_display_resolution(self, make_client):
        client, _ = make_client()
        response = client.post("/preview", data={"plugin_id": "fake"})
        assert response.status_code == 200
        assert preview_size(response) == (800, 480)

    def test_vertical_orientation_swaps_dimensions_without_rotating(self, make_client):
        client, _ = make_client(
            plugin=FakePlugin(image_size=(480, 800)),
            device_config=FakeDeviceConfig(orientation="vertical"),
        )
        response = client.post("/preview", data={"plugin_id": "fake"})
        assert preview_size(response) == (480, 800)


class TestPreviewRenderLock:

    def test_renders_while_holding_shared_lock(self, make_client):
        client, plugin = make_client()
        client.post("/preview", data={"plugin_id": "fake"})
        assert plugin.lock_held is True
        assert not RENDER_LOCK.locked()

    def test_returns_503_when_render_lock_is_busy(self, make_client, monkeypatch):
        client, plugin = make_client()
        monkeypatch.setattr(plugin_module, "PREVIEW_LOCK_TIMEOUT_S", 0.1)
        assert RENDER_LOCK.acquire(timeout=1)
        try:
            response = client.post("/preview", data={"plugin_id": "fake"})
        finally:
            RENDER_LOCK.release()
        assert response.status_code == 503
        assert plugin.received_settings is None

    def test_releases_lock_when_plugin_raises(self, make_client):
        plugin = FakePlugin()
        plugin.generate_image = lambda settings, device_config: (_ for _ in ()).throw(RuntimeError("boom"))
        client, _ = make_client(plugin=plugin)
        response = client.post("/preview", data={"plugin_id": "fake"})
        assert response.status_code == 500
        assert not RENDER_LOCK.locked()


class TestPreviewUploads:

    def png_bytes(self):
        buffer = BytesIO()
        Image.new("RGB", (10, 10), "red").save(buffer, format="PNG")
        buffer.seek(0)
        return buffer

    def test_returns_saved_path_for_uploaded_file(self, make_client, tmp_path):
        client, plugin = make_client()
        response = client.post(
            "/preview",
            data={"plugin_id": "fake", "backgroundImageFile": (self.png_bytes(), "bg.png")},
            content_type="multipart/form-data",
        )
        saved_path = response.get_json()["uploaded_files"]["backgroundImageFile"]
        assert saved_path == str(tmp_path / "static" / "images" / "saved" / "bg.png")
        assert os.path.exists(saved_path)
        assert plugin.received_settings["backgroundImageFile"] == saved_path

    def test_reused_path_is_passed_through_without_writing(self, make_client, tmp_path):
        client, plugin = make_client()
        saved_path = str(tmp_path / "static" / "images" / "saved" / "bg.png")
        response = client.post("/preview", data={"plugin_id": "fake", "backgroundImageFile": saved_path})
        assert response.get_json()["uploaded_files"] == {}
        assert plugin.received_settings["backgroundImageFile"] == saved_path
        assert not os.path.exists(saved_path)
