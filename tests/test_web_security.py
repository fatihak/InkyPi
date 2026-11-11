import io
import os
import sys

import pytest
from dotenv import dotenv_values
from PIL import Image
from werkzeug.datastructures import FileStorage, MultiDict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils import app_utils  # noqa: E402
from utils.app_utils import (filter_upload_paths, handle_request_files,  # noqa: E402
                             is_cross_origin_request)
from blueprints.apikeys import quote_env_value, write_env_file  # noqa: E402
from plugins.image_upload.image_upload import ImageUpload  # noqa: E402


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    d = tmp_path / "saved"
    d.mkdir()
    monkeypatch.setattr(app_utils, "get_upload_dir", lambda: str(d))
    return d


def _jpeg_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, "JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------- path safety

def test_cleanup_never_deletes_outside_upload_dir(upload_dir, tmp_path):
    victim = tmp_path / "device.json"
    victim.write_text("{}")
    inside = upload_dir / "a.png"
    inside.write_text("x")
    ImageUpload({"id": "image_upload"}).cleanup(
        {"imageFiles[]": [str(victim), str(upload_dir / ".." / "device.json"), str(inside)]})
    assert victim.exists()
    assert not inside.exists()


def test_filter_upload_paths_rejects_traversal(upload_dir):
    ok = str(upload_dir / "a.png")
    assert filter_upload_paths([ok, "/etc/passwd", str(upload_dir / ".." / "x.png"), None]) == [ok]


# ---------------------------------------------------------------- uploads

def test_same_name_uploads_do_not_overwrite(upload_dir):
    files = MultiDict([("imageFiles[]", FileStorage(io.BytesIO(b"a"), filename="IMG.png")),
                       ("imageFiles[]", FileStorage(io.BytesIO(b"b"), filename="IMG.png"))])
    paths = handle_request_files(files)["imageFiles[]"]
    assert len(set(paths)) == 2
    assert sorted(open(p, "rb").read() for p in paths) == [b"a", b"b"]


def test_uppercase_jpg_and_existing_paths_filtered(upload_dir):
    existing = str(upload_dir / "old.png")
    files = MultiDict([("imageFiles[]", FileStorage(io.BytesIO(_jpeg_bytes()), filename="PHOTO.JPG"))])
    form = MultiDict([("imageFiles[]", existing), ("imageFiles[]", "/etc/shadow")])
    paths = handle_request_files(files, form)["imageFiles[]"]
    assert paths[0] == existing and len(paths) == 2
    assert paths[1].endswith("_PHOTO.JPG")
    with Image.open(paths[1]) as img:
        assert img.size == (10, 10)


def test_undecodable_jpeg_is_saved_whole(upload_dir):
    data = b"\xff\xd8\xff" + b"garbage" * 100
    files = MultiDict([("f", FileStorage(io.BytesIO(data), filename="broken.jpg"))])
    path = handle_request_files(files)["f"]
    assert open(path, "rb").read() == data


def test_pdf_no_longer_accepted(upload_dir):
    files = MultiDict([("f", FileStorage(io.BytesIO(b"%PDF"), filename="doc.pdf"))])
    assert handle_request_files(files) == {}


# ---------------------------------------------------------------- CSRF

@pytest.mark.parametrize("origin,fetch_site,host,expected", [
    (None, None, "inkypi.local", False),                       # curl / scripts
    ("http://inkypi.local", None, "inkypi.local", False),       # same origin
    ("http://192.168.1.108", None, "192.168.1.108", False),
    ("http://evil.example", None, "inkypi.local", True),        # cross-site form
    ("null", None, "inkypi.local", True),                       # sandboxed iframe
    (None, "cross-site", "inkypi.local", True),
    (None, "same-origin", "inkypi.local", False),
])
def test_cross_origin_detection(origin, fetch_site, host, expected):
    assert is_cross_origin_request(origin, fetch_site, host) is expected


# ---------------------------------------------------------------- .env

@pytest.mark.parametrize("value", ['ab"c', "with space", "a#b", "back\\slash", "q'uote", ""])
def test_env_values_round_trip(tmp_path, value):
    path = tmp_path / ".env"
    assert write_env_file(str(path), [("KEY", value), ("OTHER", "x")])
    assert dotenv_values(str(path)) == {"KEY": value, "OTHER": "x"}
    assert (os.stat(path).st_mode & 0o777) == 0o600


def test_env_quote_is_always_quoted():
    assert quote_env_value("abc") == '"abc"'


# ---------------------------------------------------------------- review follow-ups

def test_cross_origin_compares_scheme_and_port():
    assert is_cross_origin_request("https://inkypi.local", None, "inkypi.local", "http")
    assert not is_cross_origin_request("http://inkypi.local:80", None, "inkypi.local", "http")
    assert is_cross_origin_request("http://inkypi.local:8080", None, "inkypi.local", "http")
    assert not is_cross_origin_request("http://localhost:8080", None, "localhost:8080", "http")


def test_long_upload_names_are_shortened(upload_dir):
    name = "a" * 250 + ".png"
    files = MultiDict([("f", FileStorage(io.BytesIO(b"x"), filename=name))])
    path = handle_request_files(files)["f"]
    assert os.path.exists(path) and len(os.path.basename(path)) < 130 and path.endswith(".png")


def test_shared_uploads_are_kept_until_unreferenced(upload_dir):
    from model import PlaylistManager, Playlist
    from utils.app_utils import collect_upload_paths, referenced_upload_paths
    shared = str(upload_dir / "shared.png")
    own = str(upload_dir / "own.png")
    manager = PlaylistManager([Playlist("P", "00:00", "24:00", [
        {"plugin_id": "image_upload", "name": "a", "plugin_settings": {"imageFiles[]": [shared, own]}, "refresh": {}},
        {"plugin_id": "image_upload", "name": "b", "plugin_settings": {"imageFiles[]": [shared],
                                                                       "backgroundImageFile": own}, "refresh": {}},
    ])])
    a, b = manager.playlists[0].plugins
    assert collect_upload_paths(b.settings) == {shared, own}
    assert referenced_upload_paths(manager, exclude=a) == {shared, own}
    assert referenced_upload_paths(manager, exclude=b) == {shared, own}


def test_removing_an_image_keeps_files_used_by_a_save_as_copy(upload_dir):
    from unittest import mock
    from flask import Flask
    from model import PlaylistManager, Playlist
    from blueprints import plugin as plugin_module
    shared, extra = upload_dir / "shared.png", upload_dir / "extra.png"
    shared.write_bytes(b"s")
    extra.write_bytes(b"e")
    manager = PlaylistManager([Playlist("P", "00:00", "24:00", [
        {"plugin_id": "image_upload", "name": "A", "plugin_settings": {"imageFiles[]": [str(shared), str(extra)]}, "refresh": {}},
        {"plugin_id": "image_upload", "name": "B", "plugin_settings": {"imageFiles[]": [str(shared)]}, "refresh": {}},
    ])])
    app = Flask(__name__)
    app.register_blueprint(plugin_module.plugin_bp)
    config = mock.Mock()
    config.get_playlist_manager.return_value = manager
    app.config["DEVICE_CONFIG"] = config
    # Edit A and remove both images from its list
    response = app.test_client().put("/update_plugin_instance/A", data={"plugin_id": "image_upload", "padImage": "true"})
    assert response.status_code == 200
    assert shared.exists()          # still used by B
    assert not extra.exists()       # only A used it
