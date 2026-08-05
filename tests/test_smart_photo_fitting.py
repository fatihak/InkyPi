from io import BytesIO

import pytest
from PIL import Image

from model import PluginInstance
from utils.image_loader import AdaptiveImageLoader
from utils.image_utils import resize_image
from utils.settings_migrations import migrate_plugin_settings


def load_fitted_image(
    image_size,
    display_size,
    fit_mode,
    background_option="color",
    background_color="#ffffff",
):
    data = BytesIO()
    Image.new("RGB", image_size, "red").save(data, format="PNG")
    data.seek(0)

    loader = AdaptiveImageLoader()
    loader.is_low_resource = False
    return loader.from_bytesio(
        data,
        display_size,
        fit_mode=fit_mode,
        background_option=background_option,
        background_color=background_color,
    )


@pytest.mark.parametrize(
    "image_size,display_size,expects_padding",
    [
        ((400, 800), (800, 480), True),
        ((800, 400), (800, 480), False),
        ((600, 600), (800, 480), False),
        ((800, 400), (480, 800), True),
        ((400, 800), (480, 800), False),
    ],
)
def test_smart_fit_uses_orientation_to_choose_contain_or_cover(
    image_size, display_size, expects_padding
):
    result = load_fitted_image(
        image_size,
        display_size,
        "auto",
    )

    assert result.size == display_size
    assert (result.getpixel((0, 0)) == (255, 255, 255)) is expects_padding
    assert result.getpixel((display_size[0] // 2, display_size[1] // 2)) == (255, 0, 0)


@pytest.mark.parametrize(
    "settings,expected",
    [
        ({"fitMode": "cover"}, "cover"),
        ({"fitMode": "contain"}, "contain"),
        ({"fitMode": "auto"}, "auto"),
        ({"fitMode": "auto", "padImage": "true"}, "auto"),
        ({"fitMode": "cover", "padImage": "true"}, "cover"),
        ({"padImage": "false"}, "cover"),
        ({"padImage": "true"}, "contain"),
        ({}, "cover"),
    ],
)
def test_fit_mode_supports_new_and_legacy_settings(settings, expected):
    migrated = migrate_plugin_settings("image_upload", settings)
    assert migrated["fitMode"] == expected


@pytest.mark.parametrize(
    "settings,expected",
    [
        ({"padImage": "true"}, "contain"),
        ({"padImage": "false"}, "cover"),
        ({"fitMode": "auto", "padImage": "true"}, "auto"),
    ],
)
def test_legacy_fit_settings_are_converted_and_removed(settings, expected):
    migrated = migrate_plugin_settings("image_upload", settings)
    assert migrated["fitMode"] == expected
    assert "padImage" not in migrated


def test_migrated_settings_serialize_without_pad_image():
    plugin_instance = PluginInstance(
        plugin_id="image_upload",
        name="Photos",
        settings={"padImage": "true"},
        refresh={"interval": 3600},
    )

    saved_settings = plugin_instance.to_dict()["plugin_settings"]
    assert saved_settings["fitMode"] == "contain"
    assert "padImage" not in saved_settings


def test_replacing_instance_settings_uses_the_central_migration():
    plugin_instance = PluginInstance(
        plugin_id="image_folder",
        name="Photos",
        settings={"fitMode": "cover"},
        refresh={"interval": 3600},
    )

    plugin_instance.settings = {"fitMode": "auto", "padImage": "true"}

    assert plugin_instance.settings == {"fitMode": "auto"}


def test_unrelated_plugin_settings_are_not_modified():
    settings = {"padImage": "true"}

    migrated = migrate_plugin_settings("weather", settings)

    assert migrated is settings
    assert migrated == {"padImage": "true"}


def test_existing_cover_and_contain_modes_remain_explicit():
    covered = load_fitted_image((400, 800), (800, 480), "cover")
    contained = load_fitted_image(
        (800, 400),
        (800, 480),
        "contain",
    )

    assert covered.getpixel((0, 0)) == (255, 0, 0)
    assert contained.getpixel((0, 0)) == (255, 255, 255)


def test_fit_mode_takes_precedence_over_legacy_resize_flag():
    data = BytesIO()
    Image.new("RGB", (400, 800), "red").save(data, format="PNG")
    data.seek(0)

    loader = AdaptiveImageLoader()
    loader.is_low_resource = False
    result = loader.from_bytesio(
        data,
        (800, 480),
        resize=False,
        fit_mode="contain",
        background_option="color",
        background_color="#ffffff",
    )

    assert result.size == (800, 480)
    assert result.getpixel((0, 0)) == (255, 255, 255)


@pytest.mark.parametrize(
    "resize,expected_size",
    [
        (True, (800, 480)),
        (False, (400, 800)),
    ],
)
def test_legacy_resize_interface_is_preserved(resize, expected_size):
    data = BytesIO()
    Image.new("RGB", (400, 800), "red").save(data, format="PNG")
    data.seek(0)

    loader = AdaptiveImageLoader()
    loader.is_low_resource = False
    result = loader.from_bytesio(data, (800, 480), resize=resize)

    assert result.size == expected_size


@pytest.mark.parametrize("is_low_resource", [False, True])
def test_file_loader_applies_auto_fit_on_all_device_types(tmp_path, is_low_resource):
    image_path = tmp_path / "portrait.jpg"
    Image.new("RGB", (400, 800), "red").save(image_path)

    loader = AdaptiveImageLoader()
    loader.is_low_resource = is_low_resource
    result = loader.from_file(
        image_path,
        (800, 480),
        fit_mode="auto",
        background_option="color",
        background_color="#ffffff",
    )

    assert result.size == (800, 480)
    assert result.getpixel((0, 0)) == (255, 255, 255)


@pytest.mark.parametrize("is_low_resource", [False, True])
def test_url_loader_applies_auto_fit_on_all_device_types(monkeypatch, is_low_resource):
    data = BytesIO()
    Image.new("RGB", (400, 800), "red").save(data, format="PNG")
    image_bytes = data.getvalue()

    class Response:
        content = image_bytes

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield image_bytes

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr("utils.image_loader.get_http_session", lambda: Session())

    loader = AdaptiveImageLoader()
    loader.is_low_resource = is_low_resource
    result = loader.from_url(
        "https://example.com/portrait.png",
        (800, 480),
        fit_mode="auto",
        background_option="color",
        background_color="#ffffff",
    )

    assert result.size == (800, 480)
    assert result.getpixel((0, 0)) == (255, 255, 255)


def test_url_loader_returns_none_when_download_fails(monkeypatch):
    class Session:
        def get(self, *args, **kwargs):
            raise RuntimeError("download failed")

    monkeypatch.setattr("utils.image_loader.get_http_session", lambda: Session())

    loader = AdaptiveImageLoader()
    assert loader.from_url("https://example.com/missing.jpg", (800, 480)) is None


def test_display_resize_preserves_legacy_cover_behavior():
    result = resize_image(Image.new("RGB", (400, 800), "red"), (800, 480))

    assert result.size == (800, 480)
    assert result.getpixel((0, 0)) == (255, 0, 0)


def test_keep_width_remains_unchanged():
    result = resize_image(
        Image.new("RGB", (400, 800), "red"),
        (800, 480),
        image_settings=["keep-width"],
    )

    assert result.size == (800, 480)
    assert result.getpixel((0, 0)) == (255, 0, 0)


@pytest.mark.parametrize(
    "resize_method",
    ["_resize_high_performance", "_resize_low_resource"],
)
def test_adaptive_loader_preserves_legacy_cover_behavior(resize_method):
    loader = AdaptiveImageLoader()

    result = getattr(loader, resize_method)(
        Image.new("RGB", (400, 800), "red"),
        (800, 480),
    )

    assert result.size == (800, 480)
    assert result.getpixel((0, 0)) == (255, 0, 0)
