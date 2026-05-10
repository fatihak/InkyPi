import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from model import Playlist, PlaylistManager, RefreshInfo
from refresh_task import RefreshTask


class FakeConfig:
    def __init__(self, interval_seconds=3600):
        self.interval_seconds = interval_seconds

    def get_config(self, key=None, default={}):
        values = {
            "plugin_cycle_interval_seconds": self.interval_seconds,
            "timezone": "UTC",
        }
        if key is None:
            return values
        return values.get(key, default)


def plugin_data(plugin_id, name):
    return {
        "plugin_id": plugin_id,
        "name": name,
        "plugin_settings": {},
        "refresh": {},
    }


def test_determine_next_plugin_can_ignore_cycle_interval():
    current_dt = datetime.now()
    latest_refresh = RefreshInfo(
        refresh_type="Playlist",
        plugin_id="clock",
        refresh_time=(current_dt - timedelta(seconds=30)).isoformat(),
        image_hash="same-image",
        playlist="Default",
        plugin_instance="Clock",
    )
    playlist = Playlist(
        "Default",
        "00:00",
        "24:00",
        plugins=[
            plugin_data("clock", "Clock"),
            plugin_data("weather", "Weather"),
        ],
    )
    playlist_manager = PlaylistManager([playlist])
    refresh_task = RefreshTask(FakeConfig(interval_seconds=3600), display_manager=None)

    inactive_playlist, inactive_plugin = refresh_task._determine_next_plugin(
        playlist_manager,
        latest_refresh,
        current_dt,
    )
    assert inactive_playlist is None
    assert inactive_plugin is None

    active_playlist, active_plugin = refresh_task._determine_next_plugin(
        playlist_manager,
        latest_refresh,
        current_dt,
        ignore_cycle_interval=True,
    )
    assert active_playlist == playlist
    assert active_plugin.name == "Clock"

    _, next_plugin = refresh_task._determine_next_plugin(
        playlist_manager,
        latest_refresh,
        current_dt,
        ignore_cycle_interval=True,
    )
    assert next_plugin.name == "Weather"


def test_cycle_playlist_next_signals_background_thread_without_rendering():
    refresh_task = RefreshTask(FakeConfig(), display_manager=None)
    refresh_task.running = True

    assert refresh_task.cycle_playlist_next() is True
    assert refresh_task.playlist_cycle_requested is True
    assert not refresh_task.refresh_event.is_set()


def test_cycle_playlist_next_returns_false_when_task_is_stopped():
    refresh_task = RefreshTask(FakeConfig(), display_manager=None)

    assert refresh_task.cycle_playlist_next() is False
    assert refresh_task.playlist_cycle_requested is False
