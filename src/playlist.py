import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class PlaylistManager:
    """Manages multiple time-based playlists."""

    def __init__(self, playlists=[]):
        self.playlists = playlists
    
    def get_playlists(self):
        return self.playlists
    
    def get_playlist_names(self):
        return [p.name for p in self.playlists]

    def add_default_playlist(self):
        return self.playlists.append(Playlist("Default", "00:00", "24:00", []))

    def get_active_playlist(self):
        """Determine the active playlist based on the current time."""
        current_time = datetime.utcnow().strftime("%H:%M")  # Get current time in "HH:MM" format
        for playlist in self.playlists:
            if playlist.is_active(current_time):
                return playlist.to_dict()
        return {}
    
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

    def add_playlist(self, name, start_time, end_time):
        """Create a new time-based playlist."""
        self.playlists.append(Playlist(name, start_time, end_time))
        return True

    def delete_playlist(self, name):
        """Remove a playlist."""
        self.playlists = [p for p in self.playlists if p.name != name]

    def to_list(self):
        """Convert all playlists to a list of dictionaries."""
        return [p.to_dict() for p in self.playlists]

    @classmethod
    def from_list(cls, playlist_list=None):
        """Create a PlaylistManager instance from a list of dictionaries."""
        playlist_list = [Playlist.from_dict(p) for p in (playlist_list or [])]
        return cls(playlists=playlist_list)

class Playlist:
    """Represents a playlist with a time-based schedule."""

    def __init__(self, name, start_time, end_time, plugins=None):
        self.name = name
        self.start_time = start_time
        self.end_time = end_time
        self.plugins = [Plugin.from_dict(p) for p in (plugins or [])]

    def is_active(self, current_time):
        """Check if the playlist is active at the given time."""
        return self.start_time <= current_time < self.end_time

    def add_plugin(self, plugin_data):
        """Add a new plugin instance to the playlist."""
        if self.find_plugin(plugin_data["plugin_id"], plugin_data["instance"]):
            logger.warning(f"Plugin '{plugin_data['plugin_id']}' with instance '{plugin_data['instance']}' already exists.")
            return False
        self.plugins.append(Plugin.from_dict(plugin_data))
        return True

    def update_plugin(self, plugin_id, instance, updated_data):
        """Update an existing plugin instance in the playlist."""
        plugin = self.find_plugin(plugin_id, instance)
        if plugin:
            plugin.update(updated_data)
            return True
        logger.warning(f"Plugin '{plugin_id}' with instance '{instance}' not found.")
        return False

    def delete_plugin(self, plugin_id, instance):
        """Remove a specific plugin instance from the playlist."""
        initial_count = len(self.plugins)
        self.plugins = [p for p in self.plugins if not (p.plugin_id == plugin_id and p.instance == instance)]
        
        if len(self.plugins) == initial_count:
            logger.warning(f"Plugin '{plugin_id}' with instance '{instance}' not found.")
            return False
        return True

    def find_plugin(self, plugin_id, instance):
        """Find a plugin instance by its plugin_id and instance."""
        return next((p for p in self.plugins if p.plugin_id == plugin_id and p.instance == instance), None)

    def to_dict(self):
        """Convert the playlist to a dictionary."""
        return {
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "plugins": [p.to_dict() for p in self.plugins]
        }

    @classmethod
    def from_dict(cls, data):
        """Create a Playlist instance from a dictionary."""
        return cls(name=data["name"], start_time=data["start_time"], end_time=data["end_time"], plugins=data["plugins"])

class Plugin:
    """Represents an individual plugin instance within a playlist."""

    def __init__(self, plugin_id, instance, settings, interval, latest_refresh=None):
        self.plugin_id = plugin_id
        self.instance = instance
        self.settings = settings
        self.interval = interval
        self.latest_refresh = latest_refresh or datetime.utcnow().isoformat()

    def update(self, updated_data):
        """Update plugin settings and refresh timestamp."""
        for key, value in updated_data.items():
            setattr(self, key, value)
        self.latest_refresh = datetime.utcnow().isoformat()

    def to_dict(self):
        """Convert plugin instance to dictionary format."""
        return {
            "plugin_id": self.plugin_id,
            "instance": self.instance,
            "plugin_settings": self.settings,
            "interval": self.interval,
            "latest_refresh": self.latest_refresh
        }

    @classmethod
    def from_dict(cls, data):
        """Create a Plugin instance from a dictionary."""
        return cls(
            plugin_id=data["plugin_id"],
            instance=data["instance"],
            settings=data["plugin_settings"],
            interval=data["interval"],
            latest_refresh=data.get("latest_refresh", {})
        )