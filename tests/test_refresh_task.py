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
            "plugin_cycle_interval_seconds": 600,
            "timezone": "UTC",
        }
        self.playlist_manager = playlist_manager or PlaylistManager()
        self.refresh_info = refresh_info or RefreshInfo(
            refresh_type="Playlist",
            plugin_id="clock",
            refresh_time=datetime.now(pytz.UTC).isoformat(),
            image_hash=0,
            playlist="Test Playlist",
            plugin_instance="Clock",
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


def make_refresh_info(plugin_instance="Clock", refresh_time=None, image_hash=0):
    if refresh_time is None:
        refresh_time = datetime.now(pytz.UTC).isoformat()
    return RefreshInfo(
        refresh_type="Playlist",
        plugin_id="clock",
        refresh_time=refresh_time,
        image_hash=image_hash,
        playlist="Test Playlist",
        plugin_instance=plugin_instance,
    )


class TestGetSleepTime:
    def test_returns_global_interval_when_no_playlist(self):
        device_config = MockDeviceConfig()
        task = RefreshTask(device_config, MockDisplayManager())

        sleep_time = task._get_sleep_time()
        assert sleep_time == 600

    def test_returns_global_interval_when_no_plugin_interval(self):
        plugin = make_plugin_instance(refresh={})
        playlist = make_playlist([plugin])
        manager = PlaylistManager(playlists=[playlist])
        device_config = MockDeviceConfig(playlist_manager=manager)
        task = RefreshTask(device_config, MockDisplayManager())

        sleep_time = task._get_sleep_time()
        assert sleep_time == pytest.approx(600, abs=1)

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
        assert sleep_time == pytest.approx(600, abs=1)


class TestDetermineNextPlugin:
    def test_refreshes_current_plugin_when_its_interval_elapsed(self):
        """A clock with interval 60 is refreshed in place while it's the current plugin."""
        # Current plugin needs refresh (interval elapsed)
        latest_refresh = (datetime.now(pytz.UTC) - timedelta(seconds=120)).isoformat()
        plugin = make_plugin_instance(refresh={"interval": 60}, latest_refresh_time=latest_refresh)
        playlist = make_playlist([plugin], current_plugin_index=0)
        manager = PlaylistManager(playlists=[playlist])

        device_config = MockDeviceConfig(playlist_manager=manager)
        task = RefreshTask(device_config, MockDisplayManager())

        # Set global refresh info to be recent so global check would fail
        device_config.refresh_info = make_refresh_info(refresh_time=datetime.now(pytz.UTC).isoformat())

        result_playlist, result_plugin = task._determine_next_plugin(
            manager, device_config.get_refresh_info(), datetime.now(pytz.UTC)
        )

        assert result_playlist == playlist
        assert result_plugin.name == plugin.name
        # Should NOT have rotated to a different plugin
        assert playlist.current_plugin_index == 0

    def test_rotates_to_next_plugin_when_global_interval_elapsed(self):
        """When plugin_cycle_interval_seconds has elapsed, the playlist advances
        to the next plugin even if the current plugin has a refresh interval."""
        # Current plugin doesn't need refresh (recently refreshed)
        latest_refresh = datetime.now(pytz.UTC).isoformat()
        plugin1 = make_plugin_instance(name="Clock1", refresh={"interval": 60}, latest_refresh_time=latest_refresh)
        plugin2 = make_plugin_instance(name="Clock2", refresh={"interval": 60}, latest_refresh_time=latest_refresh)
        playlist = make_playlist([plugin1, plugin2], current_plugin_index=0)
        manager = PlaylistManager(playlists=[playlist])

        device_config = MockDeviceConfig(playlist_manager=manager)
        # Set global refresh info to be old so global check passes
        device_config.refresh_info = make_refresh_info(
            plugin_instance="Clock1",
            refresh_time=(datetime.now(pytz.UTC) - timedelta(seconds=700)).isoformat(),
        )

        task = RefreshTask(device_config, MockDisplayManager())

        result_playlist, result_plugin = task._determine_next_plugin(
            manager, device_config.get_refresh_info(), datetime.now(pytz.UTC)
        )

        assert result_playlist == playlist
        assert result_plugin.name == plugin2.name
        assert playlist.current_plugin_index == 1

    def test_rotates_to_next_plugin_even_when_current_plugin_needs_refresh(self):
        """When the global rotation interval has elapsed, the playlist advances
        to the next plugin even if the current plugin's own refresh interval
        has also elapsed. Rotation takes priority."""
        # Current plugin needs refresh (interval elapsed)
        current_plugin_refresh = (datetime.now(pytz.UTC) - timedelta(seconds=120)).isoformat()
        plugin1 = make_plugin_instance(name="Clock1", refresh={"interval": 60}, latest_refresh_time=current_plugin_refresh)
        plugin2 = make_plugin_instance(name="Clock2", refresh={"interval": 60}, latest_refresh_time=datetime.now(pytz.UTC).isoformat())
        playlist = make_playlist([plugin1, plugin2], current_plugin_index=0)
        manager = PlaylistManager(playlists=[playlist])

        device_config = MockDeviceConfig(playlist_manager=manager)
        # Set global refresh info to be old so rotation check passes
        device_config.refresh_info = make_refresh_info(
            plugin_instance="Clock1",
            refresh_time=(datetime.now(pytz.UTC) - timedelta(seconds=700)).isoformat(),
        )

        task = RefreshTask(device_config, MockDisplayManager())

        result_playlist, result_plugin = task._determine_next_plugin(
            manager, device_config.get_refresh_info(), datetime.now(pytz.UTC)
        )

        assert result_playlist == playlist
        assert result_plugin.name == plugin2.name
        assert playlist.current_plugin_index == 1

    def test_new_plugin_can_refresh_after_rotation(self):
        """After rotation, the new plugin can be refreshed according to its own interval."""
        # Current plugin (Clock1) doesn't need refresh, but global rotation is due
        current_plugin_refresh = datetime.now(pytz.UTC).isoformat()
        plugin1 = make_plugin_instance(name="Clock1", refresh={"interval": 60}, latest_refresh_time=current_plugin_refresh)
        # New plugin (Clock2) needs refresh (interval elapsed)
        new_plugin_refresh = (datetime.now(pytz.UTC) - timedelta(seconds=120)).isoformat()
        plugin2 = make_plugin_instance(name="Clock2", refresh={"interval": 60}, latest_refresh_time=new_plugin_refresh)
        playlist = make_playlist([plugin1, plugin2], current_plugin_index=0)
        manager = PlaylistManager(playlists=[playlist])

        device_config = MockDeviceConfig(playlist_manager=manager)
        device_config.refresh_info = make_refresh_info(
            plugin_instance="Clock1",
            refresh_time=(datetime.now(pytz.UTC) - timedelta(seconds=700)).isoformat(),
        )

        task = RefreshTask(device_config, MockDisplayManager())

        # First call: rotation happens
        result_playlist, result_plugin = task._determine_next_plugin(
            manager, device_config.get_refresh_info(), datetime.now(pytz.UTC)
        )
        assert result_plugin.name == plugin2.name
        assert playlist.current_plugin_index == 1

        # Simulate the rotation refresh completing: update refresh_info to point to Clock2
        device_config.refresh_info = make_refresh_info(
            plugin_instance="Clock2",
            refresh_time=datetime.now(pytz.UTC).isoformat(),
        )

        # Second call: Clock2 needs refresh (its interval elapsed)
        result_playlist, result_plugin = task._determine_next_plugin(
            manager, device_config.get_refresh_info(), datetime.now(pytz.UTC)
        )
        assert result_plugin.name == plugin2.name
        assert playlist.current_plugin_index == 1  # Still on Clock2

    def test_returns_none_when_no_refresh_needed(self):
        """No unnecessary refreshes before expiry."""
        # Current plugin doesn't need refresh, and global interval hasn't elapsed
        latest_refresh = datetime.now(pytz.UTC).isoformat()
        plugin = make_plugin_instance(refresh={"interval": 60}, latest_refresh_time=latest_refresh)
        playlist = make_playlist([plugin], current_plugin_index=0)
        manager = PlaylistManager(playlists=[playlist])

        device_config = MockDeviceConfig(playlist_manager=manager)
        device_config.refresh_info = make_refresh_info(refresh_time=datetime.now(pytz.UTC).isoformat())

        task = RefreshTask(device_config, MockDisplayManager())

        result_playlist, result_plugin = task._determine_next_plugin(
            manager, device_config.get_refresh_info(), datetime.now(pytz.UTC)
        )

        assert result_playlist is None
        assert result_plugin is None

    def test_returns_none_when_no_active_playlist(self):
        manager = PlaylistManager(playlists=[])
        device_config = MockDeviceConfig(playlist_manager=manager)
        task = RefreshTask(device_config, MockDisplayManager())

        result_playlist, result_plugin = task._determine_next_plugin(
            manager, device_config.get_refresh_info(), datetime.now(pytz.UTC)
        )

        assert result_playlist is None
        assert result_plugin is None


class TestIsRotationRefresh:
    def test_rotation_detected_when_plugin_changes(self):
        """A rotation to a different plugin is detected."""
        refresh_info = {
            "refresh_type": "Playlist",
            "plugin_instance": "Clock2",
        }
        latest_refresh = make_refresh_info(plugin_instance="Clock1")
        task = RefreshTask(MockDeviceConfig(), MockDisplayManager())

        assert task._is_rotation_refresh(refresh_info, latest_refresh) is True

    def test_in_place_refresh_not_rotation(self):
        """An in-place refresh of the same plugin is not a rotation."""
        refresh_info = {
            "refresh_type": "Playlist",
            "plugin_instance": "Clock1",
        }
        latest_refresh = make_refresh_info(plugin_instance="Clock1")
        task = RefreshTask(MockDeviceConfig(), MockDisplayManager())

        assert task._is_rotation_refresh(refresh_info, latest_refresh) is False

    def test_manual_update_is_rotation(self):
        """A manual update is always treated as a rotation (resets rotation timer)."""
        refresh_info = {
            "refresh_type": "Manual Update",
            "plugin_instance": "Clock1",
        }
        latest_refresh = make_refresh_info(plugin_instance="Clock1")
        task = RefreshTask(MockDeviceConfig(), MockDisplayManager())

        assert task._is_rotation_refresh(refresh_info, latest_refresh) is True
