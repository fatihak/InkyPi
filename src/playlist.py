import os
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class PlaylistManager:
    """Manages multiple time-based playlists."""
    DEFAULT_PLAYLIST_START = "00:00"
    DEFAULT_PLAYLIST_END = "24:00"

    def __init__(self, playlists=[], current_playlist=None, current_plugin_index=0, latest_refresh=None):
        self.playlists = playlists
        self.current_playlist = current_playlist
        self.current_plugin_index = current_plugin_index
        self.latest_refresh = latest_refresh
    
    def get_playlists(self):
        return self.playlists
    
    def get_latest_refresh(self):
        latest_refresh = None
        if self.latest_refresh:
            latest_refresh = datetime.fromisoformat(self.latest_refresh)
        return latest_refresh
    
    def get_current_playlist_name(self):
        return self.current_playlist
    
    def get_playlist_names(self):
        return [p.name for p in self.playlists]

    def add_default_playlist(self):
        return self.playlists.append(
            Playlist("Default", PlaylistManager.DEFAULT_PLAYLIST_START, PlaylistManager.DEFAULT_PLAYLIST_END, []))
    
    def find_plugin(self, plugin_id, instance):
        """Search through all playlists to find a plugin with the given ID and instance."""
        for playlist in self.playlists:
            plugin = playlist.find_plugin(plugin_id, instance)
            if plugin:
                return plugin
        return None

    def get_active_playlist(self, current_datetime):
        """Determine the active playlist based on the current time."""
        current_time = current_datetime.strftime("%H:%M")  # Get current time in "HH:MM" format

        # get active playlists that have plugins
        active_playlists = [p for p in self.playlists if p.is_active(current_time) and p.plugins]
        if not active_playlists:
            return None
        
        # Sort playlists by priority
        active_playlists.sort(key=lambda p: p.get_priority())
        return active_playlists[0]  # Return the playlist with the smaller priority value
    
    def get_playlist(self, playlist_name):
        """Retrieve a playlist by its name."""
        return next((p for p in self.playlists if p.name == playlist_name), None)

    def add_plugin_to_playlist(self, playlist_name, plugin_data):
        """Add a plugin to a specific playlist by name."""
        playlist = self.get_playlist(playlist_name)
        if playlist:
            if playlist.add_plugin(plugin_data):
                return True
        logger.warning(f"Playlist '{playlist_name}' not found.")
        return False

    def add_playlist(self, name, start_time=None, end_time=None):
        """Create a new time-based playlist."""
        if not start_time:
            start_time = PlaylistManager.DEFAULT_PLAYLIST_START
        if not end_time:
            end_time = PlaylistManager.DEFAULT_PLAYLIST_END
        self.playlists.append(Playlist(name, start_time, end_time))
        return True
    
    def update_playlist(self, old_name, new_name, start_time, end_time):
        """Update a playlist's name, start time, and end time."""
        playlist = self.get_playlist(old_name)
        if playlist:
            playlist.name = new_name
            playlist.start_time = start_time
            playlist.end_time = end_time
            return True
        logger.warning(f"Playlist '{old_name}' not found.")
        return False

    def delete_playlist(self, name):
        """Remove a playlist."""
        self.playlists = [p for p in self.playlists if p.name != name]
    
    def to_dict(self):
        """Convert manager state to JSON-compatible dict."""
        return {
            "playlists": [p.to_dict() for p in self.playlists],
            "current_playlist": self.current_playlist,
            "latest_refresh": self.latest_refresh,
            "current_plugin_index": self.current_plugin_index
        }
    
    def determine_next_plugin(self, current_datetime, refresh_interval=2*60):
        playlist = self.get_active_playlist(current_datetime)
        if not playlist:
            logger.info(f"No active playlist determined.")
            return None

        should_refresh = PlaylistManager.should_refresh(
            self.get_latest_refresh(),
            refresh_interval,
            current_datetime
        )

        if not should_refresh:
            logger.info(f"Not time to refresh.")
            return None

        playlist = self.get_active_playlist(current_datetime)
        if not playlist:
            logger.info(f"No active playlist determined.")
            return None
        self.current_playlist = playlist.name

        if playlist.name != self.get_current_playlist_name():
            self.current_playlist = playlist.name
            self.current_plugin_index = 0
        else:
            self.current_plugin_index = (self.current_plugin_index + 1) % len(playlist.plugins)

        plugin = playlist.plugins[self.current_plugin_index]

        logger.info(f"Current plugin is {plugin.name}")
        return plugin

    @classmethod
    def from_dict(cls, data):
        """Create PlaylistManager instance from a dictionary."""
        return cls(
            playlists=[Playlist.from_dict(p) for p in data.get("playlists", [])],
            current_playlist=data.get("current_playlist"),
            current_plugin_index=data.get("current_plugin_index", 0),
            latest_refresh=data.get("latest_refresh")
        )

    @staticmethod
    def should_refresh(latest_refresh, interval_seconds, current_time):
        if not latest_refresh:
            return True  # No previous refresh, so it's time to refresh

        return (current_time - latest_refresh) >= timedelta(seconds=interval_seconds)


class Playlist:
    """Represents a playlist with a time-based schedule."""

    def __init__(self, name, start_time, end_time, plugins=None):
        self.name = name
        self.start_time = start_time
        self.end_time = end_time
        self.plugins = [PluginInstance.from_dict(p) for p in (plugins or [])]

    def is_active(self, current_time):
        """Check if the playlist is active at the given time."""
        return self.start_time <= current_time < self.end_time

    def add_plugin(self, plugin_data):
        """Add a new plugin instance to the playlist."""
        if self.find_plugin(plugin_data["plugin_id"], plugin_data["name"]):
            logger.warning(f"Plugin '{plugin_data['plugin_id']}' with instance '{plugin_data['name']}' already exists.")
            return False
        self.plugins.append(PluginInstance.from_dict(plugin_data))
        return True

    def update_plugin(self, plugin_id, instance_name, updated_data):
        """Update an existing plugin instance in the playlist."""
        plugin = self.find_plugin(plugin_id, instance_name)
        if plugin:
            plugin.update(updated_data)
            return True
        logger.warning(f"Plugin '{plugin_id}' with name '{instance_name}' not found.")
        return False

    def delete_plugin(self, plugin_id, name):
        """Remove a specific plugin instance from the playlist."""
        initial_count = len(self.plugins)
        self.plugins = [p for p in self.plugins if not (p.plugin_id == plugin_id and p.name == name)]
        
        if len(self.plugins) == initial_count:
            logger.warning(f"Plugin '{plugin_id}' with instance '{name}' not found.")
            return False
        return True

    def find_plugin(self, plugin_id, name):
        """Find a plugin instance by its plugin_id and name."""
        return next((p for p in self.plugins if p.plugin_id == plugin_id and p.name == name), None)

    def to_dict(self):
        """Convert the playlist to a dictionary."""
        return {
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "plugins": [p.to_dict() for p in self.plugins]
        }
    
    def get_priority(self):
        """Determine priority of a playlist, based on the time range"""
        return self.get_time_range_minutes()
    
    def get_time_range_minutes(self):
        """Calculate the time difference in minutes between start_time and end_time.
        
        Args:
            start_time (str): Start time in "HH:MM" format.
            end_time (str): End time in "HH:MM" format.

        Returns:
            int: Difference in minutes. If end_time is before start_time, it assumes the range spans midnight.
        """
        start = datetime.strptime(self.start_time, "%H:%M")
        # Handle '24:00' by converting it to '00:00' of the next day
        if self.end_time != "24:00":
            end = datetime.strptime(self.end_time, "%H:%M")
        else:
            end = datetime.strptime("00:00", "%H:%M")
            end += timedelta(days=1)

        return int((end - start).total_seconds() // 60)

    @classmethod
    def from_dict(cls, data):
        """Create a Playlist instance from a dictionary."""
        return cls(name=data["name"], start_time=data["start_time"], end_time=data["end_time"], plugins=data["plugins"])

class PluginInstance:
    """Represents an individual plugin instance within a playlist."""

    def __init__(self, plugin_id, name, settings, refresh, latest_refresh=None):
        self.plugin_id = plugin_id
        self.name = name
        self.settings = settings
        self.refresh = refresh
        self.latest_refresh = latest_refresh

    def update(self, updated_data):
        """Update plugin settings and refresh timestamp."""
        for key, value in updated_data.items():
            setattr(self, key, value)

    def to_dict(self):
        """Convert plugin instance to dictionary format."""
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "plugin_settings": self.settings,
            "refresh": self.refresh,
            "latest_refresh": self.latest_refresh,
        }
    
    def should_refresh(self, current_time):
        latest_refresh_dt = self.get_latest_refresh()
        if not latest_refresh_dt:
            return True

        # Check for interval-based refresh
        if "interval" in self.refresh:
            interval = self.refresh.get("interval")
            if interval and (current_time - latest_refresh_dt) >= timedelta(seconds=interval):
                return True

        # Check for scheduled refresh (HH:MM format)
        if "scheduled" in self.refresh:
            scheduled_time_str = self.refresh.get("scheduled")
            scheduled_time = datetime.strptime(scheduled_time_str, "%H:%M").replace(
                year=current_time.year, month=current_time.month, day=current_time.day)

            # If the latest refresh is before the scheduled time today
            if latest_refresh_dt < scheduled_time:
                return True

        return False
    
    def get_image_path(self):
        return f"{self.plugin_id}_{self.name.replace(' ', '_')}.png"
    
    def get_latest_refresh(self):
        latest_refresh = None
        if self.latest_refresh:
            latest_refresh = datetime.fromisoformat(self.latest_refresh)
        return latest_refresh

    @classmethod
    def from_dict(cls, data):
        """Create a Plugin instance from a dictionary."""
        return cls(
            plugin_id=data["plugin_id"],
            name=data["name"],
            settings=data["plugin_settings"],
            refresh=data["refresh"],
            latest_refresh=data.get("latest_refresh"),
        )