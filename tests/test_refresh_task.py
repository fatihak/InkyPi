import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import refresh_task as refresh_task_module
from model import Playlist
from refresh_task import PlaylistRefresh, RefreshTask


class FakeDeviceConfig:
    def __init__(self, plugin_image_dir):
        self.plugin_image_dir = plugin_image_dir
        self.plugins = {
            "scoreboard": {"id": "scoreboard"},
            "clock": {"id": "clock"},
        }

    def get_plugin(self, plugin_id):
        return self.plugins.get(plugin_id)

    def get_resolution(self):
        return (300, 200)


class SkippingPlugin:
    def skip_display_condition(self, settings, device_config, current_dt):
        return "No games to display"


class DisplayablePlugin:
    def skip_display_condition(self, settings, device_config, current_dt):
        return None

    def generate_image(self, settings, device_config):
        return Image.new("RGB", device_config.get_resolution(), "white")


def test_playlist_refresh_skips_plugin_and_advances_to_next(tmp_path, monkeypatch):
    current_dt = datetime(2026, 5, 4)
    plugin_instances = [
        {
            "plugin_id": "scoreboard",
            "name": "Scoreboard",
            "plugin_settings": {},
            "refresh": {},
            "latest_refresh_time": datetime(2026, 1, 1).isoformat(),
        },
        {
            "plugin_id": "clock",
            "name": "Clock",
            "plugin_settings": {},
            "refresh": {},
        },
    ]
    playlist = Playlist("Default", "00:00", "24:00", plugin_instances, current_plugin_index=0)
    device_config = FakeDeviceConfig(str(tmp_path))
    plugins = {
        "scoreboard": SkippingPlugin(),
        "clock": DisplayablePlugin(),
    }
    monkeypatch.setattr(refresh_task_module, "get_plugin_instance", lambda config: plugins[config["id"]])

    task = RefreshTask(device_config, display_manager=None)
    action, skipped_plugins = task._get_displayable_playlist_refresh(
        PlaylistRefresh(playlist, playlist.plugins[0]),
        current_dt,
    )

    assert skipped_plugins is True
    assert action.plugin_instance.name == "Clock"
    assert playlist.current_plugin_index == 1
    assert playlist.plugins[0].latest_refresh_time == current_dt.isoformat()
    assert playlist.plugins[0].settings["_inkypi_skip_preview"] is True
    assert (tmp_path / playlist.plugins[0].get_image_path()).exists()


def test_forced_playlist_refresh_skips_plugin_without_advancing(tmp_path, monkeypatch):
    current_dt = datetime(2026, 5, 4)
    plugin_instances = [
        {
            "plugin_id": "scoreboard",
            "name": "Scoreboard",
            "plugin_settings": {},
            "refresh": {},
        },
        {
            "plugin_id": "clock",
            "name": "Clock",
            "plugin_settings": {},
            "refresh": {},
        },
    ]
    playlist = Playlist("Default", "00:00", "24:00", plugin_instances, current_plugin_index=0)
    device_config = FakeDeviceConfig(str(tmp_path))
    plugins = {
        "scoreboard": SkippingPlugin(),
        "clock": DisplayablePlugin(),
    }
    monkeypatch.setattr(refresh_task_module, "get_plugin_instance", lambda config: plugins[config["id"]])

    task = RefreshTask(device_config, display_manager=None)
    action, skipped_plugins = task._get_forced_playlist_refresh(
        PlaylistRefresh(playlist, playlist.plugins[0], force=True),
        current_dt,
    )

    assert action is None
    assert skipped_plugins is True
    assert playlist.current_plugin_index == 0
    assert playlist.plugins[0].latest_refresh_time == current_dt.isoformat()
    assert playlist.plugins[0].settings["_inkypi_skip_preview"] is True
    assert (tmp_path / playlist.plugins[0].get_image_path()).exists()
