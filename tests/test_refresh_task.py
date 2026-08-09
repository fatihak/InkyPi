import pytest
import pytz
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.model import Playlist, PlaylistManager, PluginInstance, RefreshInfo
from src.refresh_task import RefreshTask, PlaylistRefresh


class MockDeviceConfig:
    """Mock device config for testing."""
    def __init__(self, config=None, playlist_manager=None, refresh_info=None):
        self.config = config or {
            "plugin_cycle_interval_seconds": 3600,
            "timezone": "UTC",
        }
        self.playlist_manager = playlist_manager or PlaylistManager()
        self.refresh_info = refresh_info or RefreshInfo(
            refresh_type="Playlist",
            plugin_id="clock",
            refresh_time=datetime.now().isoformat(),
            image_hash=0,
        )
        self.plugin_image_dir = "/tmp"
        self.current_image_file = "/tmp/current.png"

    def get_config(self, key=None, default=None):
        if key is None:
            return self.config
        return self.config.get(key, default)

    def get_playlist_manager(self):
        return self.playlist_manager

    def get_refresh_info(self):
        return self.refresh_info

    def get_plugin(self, plugin_id):
        return {"id": plugin_id, "image_settings": []}

    def write_config(self):
        pass


class MockDisplayManager:
    def display_image(self, image, image_settings=[]):
        pass


def make_plugin_instance(plugin_id="clock", name="Clock", refresh=None, latest_refresh_time=None):
    return PluginInstance(
        plugin_id=plugin_id,
        name=name,
        settings={},
        refresh=refresh if refresh is not None else {"interval": 60},
        latest_refresh_time=latest_refresh_time,
    )


def make_playlist(plugins, current_plugin_index=0):
    return Playlist(
        name="Test Playlist",
        start_time="00:00",
        end_time="24:00",
        plugins=[p.to_dict() for p in plugins],
        current_plugin_index=current_plugin_index,
    )


class TestGetSleepTime:
    def test_returns_global_interval_when_no_playlist(self):
        device_config = MockDeviceConfig()
        task = RefreshTask(device_config, MockDisplayManager())

        sleep_time = task._get_sleep_time()
        assert sleep_time == 3600

    def test_returns_global_interval_when_no_plugin_interval(self):
        plugin = make_plugin_instance(refresh={})
        playlist = make_playlist([plugin])
        manager = PlaylistManager(playlists=[playlist])
        device_config = MockDeviceConfig(playlist_manager=manager)
        task = RefreshTask(device_config, MockDisplayManager())

        sleep_time = task._get_sleep_time()
        assert sleep_time == 3600

    def test_returns_plugin_interval_when_shorter_than_global(self):
        plugin = make_plugin_instance(refresh={"interval": 60})
        playlist = make_playlist([plugin])
        manager = PlaylistManager(playlists=[playlist])
        device_config = MockDeviceConfig(playlist_manager=manager)
        task = RefreshTask(device_config, MockDisplayManager())

        sleep_time = task._get_sleep_time()
        assert sleep_time == 60

    def test_returns_time_until_refresh_when_partially_elapsed(self):
        # Plugin was refreshed 30 seconds ago with a 60 second interval
        latest_refresh = (datetime.now(pytz.UTC) - timedelta(seconds=30)).isoformat()
        plugin = make_plugin_instance(refresh={"interval": 60}, latest_refresh_time=latest_refresh)
        playlist = make_playlist([plugin])
        manager = PlaylistManager(playlists=[playlist])
        device_config = MockDeviceConfig(playlist_manager=manager)
        task = RefreshTask(device_config, MockDisplayManager())

        sleep_time = task._get_sleep_time()
        # Should be ~30 seconds remaining
        assert 25 <= sleep_time <= 35

    def test_returns_global_interval_when_plugin_interval_larger(self):
        plugin = make_plugin_instance(refresh={"interval": 7200})
        playlist = make_playlist([plugin])
        manager = PlaylistManager(playlists=[playlist])
        device_config = MockDeviceConfig(playlist_manager=manager)
        task = RefreshTask(device_config, MockDisplayManager())

        sleep_time = task._get_sleep_time()
        assert sleep_time == 3600


class TestDetermineNextPlugin:
    def test_refreshes_current_plugin_when_its_interval_elapsed(self):
        # Current plugin needs refresh (interval elapsed)
        latest_refresh = (datetime.now() - timedelta(seconds=120)).isoformat()
        plugin = make_plugin_instance(refresh={"interval": 60}, latest_refresh_time=latest_refresh)
        playlist = make_playlist([plugin], current_plugin_index=0)
        manager = PlaylistManager(playlists=[playlist])

        device_config = MockDeviceConfig(playlist_manager=manager)
        task = RefreshTask(device_config, MockDisplayManager())

        # Set global refresh info to be recent so global check would fail
        device_config.refresh_info = RefreshInfo(
            refresh_type="Playlist",
            plugin_id="clock",
            refresh_time=datetime.now().isoformat(),
            image_hash=0,
        )

        result_playlist, result_plugin = task._determine_next_plugin(
            manager, device_config.get_refresh_info(), datetime.now()
        )

        assert result_playlist == playlist
        assert result_plugin.name == plugin.name
        # Should NOT have rotated to a different plugin
        assert playlist.current_plugin_index == 0

    def test_rotates_to_next_plugin_when_current_does_not_need_refresh(self):
        # Current plugin doesn't need refresh (recently refreshed)
        latest_refresh = datetime.now().isoformat()
        plugin1 = make_plugin_instance(name="Clock1", refresh={"interval": 60}, latest_refresh_time=latest_refresh)
        plugin2 = make_plugin_instance(name="Clock2", refresh={"interval": 60}, latest_refresh_time=latest_refresh)
        playlist = make_playlist([plugin1, plugin2], current_plugin_index=0)
        manager = PlaylistManager(playlists=[playlist])

        device_config = MockDeviceConfig(playlist_manager=manager)
        # Set global refresh info to be old so global check passes
        device_config.refresh_info = RefreshInfo(
            refresh_type="Playlist",
            plugin_id="clock",
            refresh_time=(datetime.now() - timedelta(hours=2)).isoformat(),
            image_hash=0,
        )

        task = RefreshTask(device_config, MockDisplayManager())

        result_playlist, result_plugin = task._determine_next_plugin(
            manager, device_config.get_refresh_info(), datetime.now()
        )

        assert result_playlist == playlist
        assert result_plugin.name == plugin2.name
        assert playlist.current_plugin_index == 1

    def test_returns_none_when_no_refresh_needed(self):
        # Current plugin doesn't need refresh, and global interval hasn't elapsed
        latest_refresh = datetime.now().isoformat()
        plugin = make_plugin_instance(refresh={"interval": 60}, latest_refresh_time=latest_refresh)
        playlist = make_playlist([plugin], current_plugin_index=0)
        manager = PlaylistManager(playlists=[playlist])

        device_config = MockDeviceConfig(playlist_manager=manager)
        device_config.refresh_info = RefreshInfo(
            refresh_type="Playlist",
            plugin_id="clock",
            refresh_time=datetime.now().isoformat(),
            image_hash=0,
        )

        task = RefreshTask(device_config, MockDisplayManager())

        result_playlist, result_plugin = task._determine_next_plugin(
            manager, device_config.get_refresh_info(), datetime.now()
        )

        assert result_playlist is None
        assert result_plugin is None

    def test_returns_none_when_no_active_playlist(self):
        manager = PlaylistManager(playlists=[])
        device_config = MockDeviceConfig(playlist_manager=manager)
        task = RefreshTask(device_config, MockDisplayManager())

        result_playlist, result_plugin = task._determine_next_plugin(
            manager, device_config.get_refresh_info(), datetime.now()
        )

        assert result_playlist is None
        assert result_plugin is None