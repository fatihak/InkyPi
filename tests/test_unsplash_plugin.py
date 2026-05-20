import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT))

from plugins.unsplash import unsplash as unsplash_module
from plugins.unsplash.unsplash import Unsplash


class DummyResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class DummySession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, dict(params or {})))
        return self.responses.pop(0)


class TestUnsplashPlugin(unittest.TestCase):
    def setUp(self):
        self.device_config = MagicMock()
        self.device_config.load_env_key.return_value = "access-key"
        self.device_config.get_resolution.return_value = (800, 480)
        self.device_config.get_config.return_value = "horizontal"

        low_resource_patcher = patch.object(unsplash_module, "_is_low_resource_device", return_value=True)
        low_resource_patcher.start()
        self.addCleanup(low_resource_patcher.stop)

        self.plugin = Unsplash({"id": "unsplash"})

        self.plugin.image_loader = MagicMock()
        self.plugin.image_loader.from_url.return_value = "image"

    def test_photo_mode_keeps_random_photo_endpoint(self):
        session = DummySession([
            DummyResponse({
                "id": "photo-id",
                "asset_type": "photo",
                "urls": {
                    "regular": "https://example.test/photo-regular.jpg",
                    "full": "https://example.test/photo-full.jpg",
                },
            })
        ])

        with patch.object(unsplash_module, "get_http_session", return_value=session):
            result = self.plugin.generate_image({
                "asset_type": "photo",
                "collections": "abc",
                "content_filter": "low",
            }, self.device_config)

        self.assertEqual(result, "image")
        self.assertEqual(session.calls, [(
            "https://api.unsplash.com/photos/random",
            {
                "client_id": "access-key",
                "content_filter": "low",
                "per_page": 100,
                "collections": "abc",
            },
        )])
        self.plugin.image_loader.from_url.assert_called_once_with(
            "https://example.test/photo-regular.jpg",
            (800, 480),
            timeout_ms=40000,
        )

    def test_illustration_mode_uses_collection_endpoint(self):
        session = DummySession([
            DummyResponse([
                {
                    "id": "photo-id",
                    "asset_type": "photo",
                    "urls": {"regular": "https://example.test/photo.jpg"},
                },
                {
                    "id": "illustration-id",
                    "asset_type": "illustration",
                    "urls": {"regular": "https://example.test/illustration.jpg"},
                },
            ])
        ])

        with patch.object(unsplash_module, "get_http_session", return_value=session):
            result = self.plugin.generate_image({
                "asset_type": "illustration",
                "collections": "Vwmvy6UieVg",
                "color": "blue",
                "orientation": "portrait",
            }, self.device_config)

        self.assertEqual(result, "image")
        self.assertEqual(session.calls, [(
            "https://api.unsplash.com/collections/Vwmvy6UieVg/photos",
            {
                "client_id": "access-key",
                "per_page": 30,
                "orientation": "portrait",
            },
        )])
        self.plugin.image_loader.from_url.assert_called_once_with(
            "https://example.test/illustration.jpg",
            (800, 480),
            timeout_ms=40000,
        )

    def test_mixed_mode_combines_multiple_collections(self):
        session = DummySession([
            DummyResponse([
                {
                    "id": "photo-id",
                    "links": {"self": "https://api.unsplash.com/photos/photo-id"},
                    "urls": {"regular": "https://example.test/photo.jpg"},
                },
            ]),
            DummyResponse([
                {
                    "id": "illustration-id",
                    "links": {"self": "https://api.unsplash.com/illustrations/illustration-id"},
                    "urls": {"regular": "https://example.test/illustration.jpg"},
                },
            ]),
        ])

        with patch.object(unsplash_module, "get_http_session", return_value=session):
            with patch.object(unsplash_module.random, "choice", side_effect=lambda items: items[-1]):
                result = self.plugin.generate_image({
                    "asset_type": "mixed",
                    "collections": "photos, illustrations",
                }, self.device_config)

        self.assertEqual(result, "image")
        self.assertEqual([call[0] for call in session.calls], [
            "https://api.unsplash.com/collections/photos/photos",
            "https://api.unsplash.com/collections/illustrations/photos",
        ])
        self.plugin.image_loader.from_url.assert_called_once_with(
            "https://example.test/illustration.jpg",
            (800, 480),
            timeout_ms=40000,
        )

    def test_illustration_mode_rejects_search_query(self):
        session = DummySession([])

        with patch.object(unsplash_module, "get_http_session", return_value=session):
            with self.assertRaisesRegex(RuntimeError, "Search query is only supported"):
                self.plugin.generate_image({
                    "asset_type": "illustration",
                    "collections": "Vwmvy6UieVg",
                    "search_query": "food",
                }, self.device_config)

        self.assertEqual(session.calls, [])

    def test_illustration_mode_errors_when_collection_has_no_matches(self):
        session = DummySession([
            DummyResponse([
                {
                    "id": "photo-id",
                    "asset_type": "photo",
                    "urls": {"regular": "https://example.test/photo.jpg"},
                },
            ])
        ])

        with patch.object(unsplash_module, "get_http_session", return_value=session):
            with self.assertRaisesRegex(RuntimeError, "No Unsplash illustration items"):
                self.plugin.generate_image({
                    "asset_type": "illustration",
                    "collections": "photos-only",
                }, self.device_config)


if __name__ == "__main__":
    unittest.main()
