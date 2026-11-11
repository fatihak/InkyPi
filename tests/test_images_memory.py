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
    assert max(img.size) <= 1600
    assert img.size[1] > img.size[0]  # EXIF rotation applied (portrait)


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
