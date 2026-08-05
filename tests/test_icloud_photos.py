import json
import os

import pytest
import requests
from PIL import Image

import plugins.icloud_photos.icloud_photos as icloud_photos
from utils.image_loader import AdaptiveImageLoader


LIVE_ALBUM_URL = "https://www.icloud.com/sharedalbum/#B2D5n8hH4GcYvKd"


class FakeResponse:
    def __init__(self, data=None, request_error=None, json_error=None):
        self.data = data
        self.request_error = request_error
        self.json_error = json_error

    def raise_for_status(self):
        if self.request_error:
            raise self.request_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.data


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeDeviceConfig:
    def __init__(self, resolution=(800, 480), orientation="horizontal"):
        self.resolution = resolution
        self.orientation = orientation

    def get_resolution(self):
        return self.resolution

    def get_config(self, key):
        if key == "orientation":
            return self.orientation
        return None


class FakeProvider:
    photos = {"photo-1": "checksum-1"}
    image = Image.new("RGB", (800, 480), "white")
    load_error = None
    last_instance = None

    def __init__(self, image_loader):
        self.image_loader = image_loader
        self.load_call = None
        type(self).last_instance = self

    def get_photos(self, stream_id):
        self.stream_id = stream_id
        return dict(self.photos)

    def load_photo(self, stream_id, guid, checksum, dimensions, resize):
        self.load_call = {
            "stream_id": stream_id,
            "guid": guid,
            "checksum": checksum,
            "dimensions": dimensions,
            "resize": resize,
        }
        if self.load_error:
            raise self.load_error
        return self.image.copy()


@pytest.mark.parametrize(
    "encoded,expected",
    [
        ("0", 0),
        ("9", 9),
        ("A", 10),
        ("Z", 35),
        ("a", 36),
        ("z", 61),
        ("10", 62),
        ("2D", 137),
    ],
)
def test_base62_decode(encoded, expected):
    assert icloud_photos.base62_decode(encoded) == expected


@pytest.mark.parametrize("encoded", ["", "-", "!", "D_"])
def test_base62_decode_rejects_invalid_values(encoded):
    with pytest.raises(ValueError):
        icloud_photos.base62_decode(encoded)


def test_get_stream_id_accepts_shared_album_url():
    assert (
        icloud_photos.get_stream_id("https://www.icloud.com/sharedalbum/#B2DAlbum123")
        == "B2DAlbum123"
    )


@pytest.mark.parametrize(
    "album_url",
    [
        "",
        "http://www.icloud.com/sharedalbum/#B2DAlbum123",
        "https://icloud.com/sharedalbum/#B2DAlbum123",
        "https://www.icloud.com.example.org/sharedalbum/#B2DAlbum123",
        "https://www.icloud.com/not-shared/#B2DAlbum123",
        "https://www.icloud.com/sharedalbum/",
        "https://www.icloud.com/sharedalbum/#invalid-id",
    ],
)
def test_get_stream_id_rejects_invalid_urls(album_url):
    with pytest.raises(RuntimeError):
        icloud_photos.get_stream_id(album_url)


@pytest.mark.parametrize(
    "stream_id,expected",
    [
        ("A1Album", 1),
        ("B2DAlbum", 137),
    ],
)
def test_get_partition(stream_id, expected):
    assert icloud_photos.get_partition(stream_id) == expected


@pytest.mark.parametrize("stream_id", ["", "A", "B2"])
def test_get_partition_rejects_short_ids(stream_id):
    with pytest.raises(RuntimeError):
        icloud_photos.get_partition(stream_id)


def test_get_photos_selects_largest_derivative_by_area():
    session = FakeSession(
        FakeResponse(
            {
                "photos": [
                    {
                        "photoGuid": "photo-1",
                        "derivatives": {
                            "wide": {
                                "width": "1400",
                                "height": "700",
                                "checksum": "wide-checksum",
                            },
                            "portrait": {
                                "width": "1000",
                                "height": "1600",
                                "checksum": "portrait-checksum",
                            },
                        },
                    },
                    {
                        "photoGuid": "malformed-photo",
                        "derivatives": {
                            "invalid": {
                                "width": "unknown",
                                "height": "600",
                                "checksum": "invalid-checksum",
                            }
                        },
                    },
                ]
            }
        )
    )
    provider = icloud_photos.ICloudSharedAlbumProvider(object(), session=session)

    photos = provider.get_photos("B2DAlbum")

    assert photos == {"photo-1": "portrait-checksum"}
    url, request = session.calls[0]
    assert url.startswith("https://p137-sharedstreams.icloud.com/")
    assert json.loads(request["data"]) == {"streamCtag": None}
    assert request["headers"] == {"Content-Type": "text/plain"}
    assert request["timeout"] == 30


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse({"photos": []}),
        FakeResponse({}),
        FakeResponse({"photos": [{"photoGuid": "photo-1", "derivatives": {}}]}),
        FakeResponse([]),
    ],
)
def test_get_photos_rejects_responses_without_usable_photos(response):
    provider = icloud_photos.ICloudSharedAlbumProvider(
        object(), session=FakeSession(response)
    )

    with pytest.raises(RuntimeError):
        provider.get_photos("B2DAlbum")


def test_get_photos_wraps_request_errors():
    provider = icloud_photos.ICloudSharedAlbumProvider(
        object(), session=FakeSession(requests.Timeout("timed out"))
    )

    with pytest.raises(RuntimeError, match="Unable to retrieve"):
        provider.get_photos("B2DAlbum")


def test_get_photos_rejects_invalid_json():
    provider = icloud_photos.ICloudSharedAlbumProvider(
        object(), session=FakeSession(FakeResponse(json_error=ValueError("invalid")))
    )

    with pytest.raises(RuntimeError, match="invalid response"):
        provider.get_photos("B2DAlbum")


def test_get_photo_url_uses_an_available_https_host(monkeypatch):
    session = FakeSession(
        FakeResponse(
            {
                "items": {
                    "checksum-1": {
                        "url_location": "assets.icloud.example",
                        "url_path": "/asset/photo.jpg?signature=secret",
                    }
                },
                "locations": {
                    "assets.icloud.example": {
                        "scheme": "https",
                        "hosts": ["host-a.example", "host-b.example"],
                    }
                },
            }
        )
    )
    provider = icloud_photos.ICloudSharedAlbumProvider(object(), session=session)
    monkeypatch.setattr(icloud_photos.random, "choice", lambda values: values[-1])

    url = provider.get_photo_url("B2DAlbum", "photo-1", "checksum-1")

    assert url == "https://host-b.example/asset/photo.jpg?signature=secret"
    _, request = session.calls[0]
    assert json.loads(request["data"]) == {"photoGuids": ["photo-1"]}


@pytest.mark.parametrize(
    "data,error",
    [
        ({"items": {}, "locations": {}}, "download location"),
        (
            {
                "items": {
                    "checksum-1": {
                        "url_location": "assets.example",
                        "url_path": "missing-leading-slash",
                    }
                },
                "locations": {},
            },
            "invalid photo download location",
        ),
        (
            {
                "items": {
                    "checksum-1": {
                        "url_location": "assets.example",
                        "url_path": "/photo.jpg",
                    }
                },
                "locations": {"assets.example": {"scheme": "http"}},
            },
            "insecure",
        ),
    ],
)
def test_get_photo_url_rejects_invalid_locations(data, error):
    provider = icloud_photos.ICloudSharedAlbumProvider(
        object(), session=FakeSession(FakeResponse(data))
    )

    with pytest.raises(RuntimeError, match=error):
        provider.get_photo_url("B2DAlbum", "photo-1", "checksum-1")


def test_select_photo_reconciles_removed_and_replaced_photos(monkeypatch):
    settings = {
        icloud_photos.VIEWED_PHOTOS_KEY: {
            "viewed": "viewed-checksum",
            "replaced": "old-checksum",
            "removed": "removed-checksum",
        }
    }
    current = {
        "viewed": "viewed-checksum",
        "replaced": "new-checksum",
        "new": "new-photo-checksum",
    }
    monkeypatch.setattr(icloud_photos.random, "choice", lambda values: values[0])

    guid, checksum, viewed = icloud_photos.ICloudPhotos._select_photo(settings, current)

    assert guid == "replaced"
    assert checksum == "new-checksum"
    assert viewed == {"viewed": "viewed-checksum"}


def test_select_photo_starts_new_cycle_when_all_photos_were_viewed(monkeypatch):
    settings = {
        icloud_photos.VIEWED_PHOTOS_KEY: {
            "photo-1": "checksum-1",
            "photo-2": "checksum-2",
        }
    }
    current = {"photo-1": "checksum-1", "photo-2": "checksum-2"}
    monkeypatch.setattr(icloud_photos.random, "choice", lambda values: values[0])

    guid, checksum, viewed = icloud_photos.ICloudPhotos._select_photo(settings, current)

    assert (guid, checksum) == ("photo-1", "checksum-1")
    assert viewed == {}


def _plugin_without_base_initialization():
    plugin = icloud_photos.ICloudPhotos.__new__(icloud_photos.ICloudPhotos)
    plugin.image_loader = object()
    return plugin


def test_generate_image_uses_loader_resize_for_cover_mode(monkeypatch):
    monkeypatch.setattr(icloud_photos, "ICloudSharedAlbumProvider", FakeProvider)
    monkeypatch.setattr(icloud_photos.random, "choice", lambda values: values[0])
    FakeProvider.photos = {"photo-1": "checksum-1"}
    FakeProvider.image = Image.new("RGB", (800, 480), "white")
    FakeProvider.load_error = None
    settings = {
        "album_url": "https://www.icloud.com/sharedalbum/#B2DAlbum123",
    }

    image = _plugin_without_base_initialization().generate_image(
        settings, FakeDeviceConfig()
    )

    assert image.size == (800, 480)
    assert FakeProvider.last_instance.load_call["dimensions"] == (800, 480)
    assert FakeProvider.last_instance.load_call["resize"] is True
    assert settings[icloud_photos.VIEWED_PHOTOS_KEY] == {
        "photo-1": "checksum-1"
    }


def test_generate_image_reverses_dimensions_and_applies_blur_padding(monkeypatch):
    monkeypatch.setattr(icloud_photos, "ICloudSharedAlbumProvider", FakeProvider)
    monkeypatch.setattr(icloud_photos.random, "choice", lambda values: values[0])
    FakeProvider.photos = {"photo-1": "checksum-1"}
    FakeProvider.image = Image.new("RGB", (1200, 800), "white")
    FakeProvider.load_error = None
    padding_calls = []

    def fake_pad_image_blur(image, dimensions):
        padding_calls.append((image.size, dimensions))
        return Image.new("RGB", dimensions, "gray")

    monkeypatch.setattr(icloud_photos, "pad_image_blur", fake_pad_image_blur)
    settings = {
        "album_url": "https://www.icloud.com/sharedalbum/#B2DAlbum123",
        "padImage": "true",
        "backgroundOption": "blur",
    }

    image = _plugin_without_base_initialization().generate_image(
        settings,
        FakeDeviceConfig(resolution=(800, 480), orientation="vertical"),
    )

    assert image.size == (480, 800)
    assert FakeProvider.last_instance.load_call["dimensions"] == (480, 800)
    assert FakeProvider.last_instance.load_call["resize"] is False
    assert padding_calls == [((1200, 800), (480, 800))]


def test_generate_image_applies_solid_color_padding(monkeypatch):
    monkeypatch.setattr(icloud_photos, "ICloudSharedAlbumProvider", FakeProvider)
    monkeypatch.setattr(icloud_photos.random, "choice", lambda values: values[0])
    FakeProvider.photos = {"photo-1": "checksum-1"}
    FakeProvider.image = Image.new("RGB", (100, 200), "black")
    FakeProvider.load_error = None
    settings = {
        "album_url": "https://www.icloud.com/sharedalbum/#B2DAlbum123",
        "padImage": "true",
        "backgroundOption": "color",
        "backgroundColor": "#ff0000",
    }

    image = _plugin_without_base_initialization().generate_image(
        settings, FakeDeviceConfig()
    )

    assert image.size == (800, 480)
    assert image.getpixel((0, 0)) == (255, 0, 0)


def test_generate_image_does_not_mark_failed_download_as_viewed(monkeypatch):
    monkeypatch.setattr(icloud_photos, "ICloudSharedAlbumProvider", FakeProvider)
    monkeypatch.setattr(icloud_photos.random, "choice", lambda values: values[0])
    FakeProvider.photos = {"photo-1": "checksum-1"}
    FakeProvider.load_error = RuntimeError("download failed")
    settings = {
        "album_url": "https://www.icloud.com/sharedalbum/#B2DAlbum123",
    }

    with pytest.raises(RuntimeError, match="download failed"):
        _plugin_without_base_initialization().generate_image(
            settings, FakeDeviceConfig()
        )

    assert icloud_photos.VIEWED_PHOTOS_KEY not in settings
    FakeProvider.load_error = None


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_ICLOUD_TESTS") != "1",
    reason="Set RUN_LIVE_ICLOUD_TESTS=1 to call the public iCloud Shared Album API.",
)
def test_live_shared_album_schema_and_image_download():
    """Verify Apple's live shared-album schema and download flow on demand."""
    stream_id = icloud_photos.get_stream_id(LIVE_ALBUM_URL)
    provider = icloud_photos.ICloudSharedAlbumProvider(AdaptiveImageLoader())

    photos = provider.get_photos(stream_id)
    assert photos
    assert all(guid and checksum for guid, checksum in photos.items())

    guid, checksum = next(iter(photos.items()))
    image = provider.load_photo(
        stream_id,
        guid,
        checksum,
        dimensions=(800, 480),
        resize=True,
    )
    try:
        assert image.size == (800, 480)
        assert image.mode in ("RGB", "L")
    finally:
        image.close()
