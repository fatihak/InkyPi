import os
import sys
from datetime import datetime, timedelta
from unittest import mock

import pytest
import pytz
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from blueprints import main as main_module  # noqa: E402
from blueprints.playlist import format_refresh_schedule, format_relative_time, playlist_bp  # noqa: E402
from model import RefreshInfo  # noqa: E402


@pytest.mark.parametrize("refresh,expected", [
    ({"interval": 600}, "Every 10 min"),
    ({"interval": 5400}, "Every 90 min"),
    ({"interval": 3600}, "Every hour"),
    ({"interval": 7200}, "Every 2 h"),
    ({"interval": 86400}, "Every day"),
    ({"scheduled": "07:30"}, "Daily at 07:30"),
    ({}, ""), (None, ""),
])
def test_format_refresh_schedule(refresh, expected):
    assert format_refresh_schedule(refresh) == expected


class FakeConfig:
    def __init__(self, time_format="24h", refresh=None):
        self.values = {"time_format": time_format, "plugin_cycle_interval_seconds": 600}
        self.refresh = refresh or RefreshInfo(None, None, None, None)

    def get_config(self, key, default=None):
        return self.values.get(key, default)

    def get_refresh_info(self):
        return self.refresh

    def get_plugins(self):
        return [{"id": "weather", "display_name": "Weather"}]


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(playlist_bp)
    return app


def test_relative_time_follows_24h_setting(app):
    tz = pytz.timezone("Europe/Paris")
    earlier = (datetime.now(tz) - timedelta(hours=3)).replace(hour=7, minute=5)
    if earlier.date() != datetime.now(tz).date():
        pytest.skip("crosses midnight")
    app.config["DEVICE_CONFIG"] = FakeConfig("24h")
    with app.app_context():
        assert format_relative_time(earlier.isoformat()) == "today at 07:05"
    app.config["DEVICE_CONFIG"] = FakeConfig("12h")
    with app.app_context():
        assert format_relative_time(earlier.isoformat()) == "today at 7:05 AM"


def test_playlist_same_start_and_end_rejected(app):
    manager = mock.Mock()
    manager.get_playlist.return_value = None
    config = mock.Mock()
    config.get_playlist_manager.return_value = manager
    app.config["DEVICE_CONFIG"] = config
    response = app.test_client().post("/create_playlist", json={
        "playlist_name": "Morning", "start_time": "07:00", "end_time": "07:00"})
    assert response.status_code == 400
    manager.add_playlist.assert_not_called()


def test_display_status(app):
    tz = pytz.timezone("Europe/Paris")
    refreshed = datetime.now(tz) - timedelta(minutes=1)
    info = RefreshInfo("Playlist", "weather", refreshed.isoformat(), "h", playlist="Default", plugin_instance="Météo")
    with app.app_context():
        app.config["DEVICE_CONFIG"] = FakeConfig("24h", info)
        status = main_module.display_status(app.config["DEVICE_CONFIG"])
    assert status["title"] == "Météo" and status["plugin"] == "Weather" and status["playlist"] == "Default"
    assert status["refreshed"] == "just now"
    assert status["next_change"] == (refreshed + timedelta(seconds=600)).strftime("%H:%M")
    empty = main_module.display_status(FakeConfig())
    assert empty["title"] == "Nothing displayed yet" and not empty["has_image"]
