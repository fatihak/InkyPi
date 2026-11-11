import os
import sys
from unittest import mock

import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils import image_loader  # noqa: E402
from utils.image_loader import AdaptiveImageLoader  # noqa: E402
from plugins.image_folder.image_folder import list_files_in_folder  # noqa: E402


@pytest.fixture
def big_rotated_jpeg(tmp_path):
    """6000x4000 landscape pixels with EXIF orientation 6 (displayed as 4000x6000 portrait)."""
    path = tmp_path / "big.jpg"
    img = Image.new("RGB", (6000, 4000), "blue")
    exif = Image.Exif()
    exif[0x0112] = 6
    img.save(path, "JPEG", exif=exif.tobytes())
    return str(path)


@pytest.mark.parametrize("low_resource", [True, False])
def test_unresized_load_is_bounded_and_oriented(big_rotated_jpeg, low_resource):
    with mock.patch.object(image_loader, "_is_low_resource_device", return_value=low_resource):
        loader = AdaptiveImageLoader()
    img = loader.from_file(big_rotated_jpeg, (800, 480), resize=False)
    assert img.size[1] > img.size[0]  # EXIF rotation applied (portrait)
    # just enough to cover twice the display (1600x960) without upscaling
    assert img.size[0] == 1600 and img.size[1] >= 960 and img.size[1] < 6000


def test_small_images_are_not_upscaled(tmp_path):
    path = tmp_path / "small.png"
    Image.new("RGB", (300, 200)).save(path)
    img = AdaptiveImageLoader().from_file(str(path), (800, 480), resize=False)
    assert img.size == (300, 200)


def test_hidden_folders_are_skipped(tmp_path):
    for rel in ["a.jpg", "sub/b.png", ".thumbnails/c.jpg", "@eaDir/d.jpg", "sub/.Trash/e.jpg", ".hidden.jpg"]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    found = sorted(os.path.relpath(f, tmp_path) for f in list_files_in_folder(str(tmp_path)))
    assert found == ["a.jpg", os.path.join("sub", "b.png")]


def test_cgroup_limit_makes_device_low_resource():
    with mock.patch.object(image_loader, "_cgroup_memory_limit", return_value=200 * 1024 * 1024):
        assert image_loader._is_low_resource_device() is True
    with mock.patch.object(image_loader, "_cgroup_memory_limit", return_value=None), \
         mock.patch.object(image_loader.psutil, "virtual_memory", return_value=mock.Mock(total=4 * 1024 ** 3)):
        assert image_loader._is_low_resource_device() is False



def test_panorama_keeps_enough_height_for_cropping(tmp_path):
    path = tmp_path / "pano.jpg"
    Image.new("RGB", (12000, 2000), "red").save(path, "JPEG")
    img = AdaptiveImageLoader().from_file(str(path), (800, 480), resize=False)
    assert img.size == (5760, 960)  # covers 1600x960; a square bound would give 1600x267


def test_png_is_shrunk_without_a_full_size_rotation_copy(tmp_path):
    path = tmp_path / "big.png"
    img = Image.new("RGB", (5000, 4000), "green")
    exif = Image.Exif()
    exif[0x0112] = 6
    img.save(path, "PNG", exif=exif.tobytes())
    loaded = AdaptiveImageLoader().from_file(str(path), (800, 480), resize=False)
    assert loaded.size[1] > loaded.size[0] and max(loaded.size) < 5000


def test_cgroup_limit_uses_smallest_ancestor(tmp_path, monkeypatch):
    root = tmp_path / "cg"
    (root / "system.slice" / "inkypi.service").mkdir(parents=True)
    (root / "memory.max").write_text("max")
    (root / "system.slice" / "memory.max").write_text(str(200 * 1024 * 1024))
    (root / "system.slice" / "inkypi.service" / "memory.max").write_text("max")
    real_open = open
    fake = mock.mock_open(read_data="0::/system.slice/inkypi.service\n")
    monkeypatch.setattr("builtins.open", lambda p, *a, **k: fake(p) if p == "/proc/self/cgroup" else real_open(p, *a, **k))
    assert image_loader._cgroup_memory_limit(str(root)) == 200 * 1024 * 1024


def test_url_fast_path_uses_draft_before_decoding(tmp_path):
    import io
    buf = io.BytesIO()
    Image.new("RGB", (6000, 4000), "blue").save(buf, "JPEG")
    buf.seek(0)
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.raw = buf
    session = mock.Mock(get=mock.Mock(return_value=response))
    with mock.patch.object(image_loader, "_is_low_resource_device", return_value=False):
        loader = AdaptiveImageLoader()
    from PIL import JpegImagePlugin
    seen = []
    real_draft = JpegImagePlugin.JpegImageFile.draft
    with mock.patch.object(image_loader, "get_http_session", return_value=session), \
         mock.patch.object(JpegImagePlugin.JpegImageFile, "draft", autospec=True,
                           side_effect=lambda self, *a: seen.append(getattr(self, "_im", None)) or real_draft(self, *a)):
        img = loader.from_url("http://example/x.jpg", (800, 480), resize=False)
    assert img.size == (1600, 1067)
    assert seen and seen[0] is None  # draft was applied before the pixels were decoded
