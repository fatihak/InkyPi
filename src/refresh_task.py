import threading
import time
import os
import logging
import pytz
from datetime import datetime, timezone
from plugins.plugin_registry import get_plugin_instance
from utils.image_utils import compute_image_hash
from model import RefreshInfo, PlaylistManager
from PIL import Image

logger = logging.getLogger(__name__)

class RefreshTask:
    """Handles the logic for refreshing the display using a backgroud thread."""

    def __init__(self, device_config, display_manager):
        self.device_config = device_config
        self.display_manager = display_manager

        self.thread = None
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.running = False
        self.manual_update_settings = ()

        self.refresh_event = threading.Event()
        self.refresh_event.set()
        self.refresh_result = {}

    def start(self):
        """Starts the background thread for refreshing the display."""
        if not self.thread or not self.thread.is_alive():
            logger.info("Starting refresh task")
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.running = True
            self.thread.start()

    def stop(self):
        """Stops the refresh task by notifying the background thread to exit."""
        with self.condition:
            self.running = False
            self.condition.notify_all()  # Wake the thread to let it exit
        if self.thread:
            logger.info("Stopping refresh task")
            self.thread.join()

    def _run(self):
        """Background task that manages the periodic refresh of the display.

        This function runs in a loop, sleeping for a configured duration (`scheduler_sleep_time`) or until manually 
        triggered via `manual_update()`. Detrmines the next plugin to refresh based on active playlists and 
        updates the display accordingly.

        Workflow:
        1. Waits for the configured sleep duration or until notified of a manual update.
        2. Checks if a manual update has been requested:
        - If so, refreshes the specified plugin immediately.
        3. Otherwise, determines the next plugin to refresh based on the active playlist and generates an image.
        4. Compares the image hash with the last displayed image hash.
        - If the image has changed, updates the display.
        - If the image is the same, skips the refresh.
        5. Updates the refresh metadata in the device configuration.
        6. Repeats the process until `stop()` is called.

        Handles any exceptions that occur during the refresh process and ensures the refresh event is set 
        to indicate completion.

        Exceptions:
        - Captures and logs any unexpected errors during execution to prevent the thread from exiting.
        """
        while True:
            try:
                with self.condition:
                    sleep_time = self.device_config.get_config("scheduler_sleep_time")

                    # Wait for sleep_time or until notified
                    self.condition.wait(timeout=sleep_time)
                    self.refresh_result = {}
                    self.refresh_event.clear()

                    # Exit if `stop()` is called
                    if not self.running:
                        break 

                    playlist_manager = self.device_config.get_playlist_manager()
                    latest_refresh = self.device_config.get_refresh_info()
                    current_dt = self._get_current_datetime()

                    image, image_settings = None, []
                    if self.manual_update_settings:
                        # handle immediate update request
                        logger.info("Manual update requested")
                        plugin_id, plugin_settings = self.manual_update_settings
                        self.manual_update_settings = ()

                        image, image_settings = self._refresh_plugin(plugin_id, plugin_settings)
                        refresh_info = {"refresh_type": "Manual Update", "plugin_id": plugin_id}
                    else:
                        # handle refresh based on playlists
                        logger.info(f"Running interval refresh check. | current_time: {current_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                        playlist, plugin_instance = self._determine_next_plugin(playlist_manager, latest_refresh, current_dt)

                        if plugin_instance:
                            image, image_settings = self._plugin_instance_refresh(plugin_instance, current_dt)

                            refresh_info = {
                                "refresh_type": "Playlist",
                                "playlist": playlist.name,
                                "plugin_id": plugin_instance.plugin_id,
                                "plugin_instance": plugin_instance.name
                            }
                    if image:
                        image_hash = compute_image_hash(image)
                        refresh_info.update({"refresh_time": current_dt.isoformat(), "image_hash": image_hash})
                        # check if image is the same as current image
                        if image_hash != latest_refresh.image_hash:
                            logger.info(f"Updating display. | refresh_info: {refresh_info}")
                            self.display_manager.display_image(image, image_settings=image_settings)
                        else:
                            logger.info(f"Image already displayed, skipping refresh. | refresh_info: {refresh_info}")

                        # update latest refresh data in the device config
                        self.device_config.refresh_info = RefreshInfo(**refresh_info)

                    self.device_config.write_config()

            except Exception as e:
                logging.exception('Exception during refresh')
                self.refresh_result["exception"] = e  # Capture exception
            finally:
                self.refresh_event.set()

    def manual_update(self, plugin_id, plugin_settings):
        """Manually triggers an update for the specified plugin id and plugin settings by notifying the background process."""
        if self.running:
            with self.condition:
                self.manual_update_settings = (plugin_id, plugin_settings)
                self.refresh_result = {}
                self.refresh_event.clear()

                self.condition.notify_all()  # Wake the thread to process manual update

            self.refresh_event.wait(timeout=60)
            if self.refresh_result.get("exception"):
                raise self.refresh_result.get("exception")
        else:
            logger.warn("Background refresh task is not running, unable to do a manual update")

    def _refresh_plugin(self, plugin_id, plugin_settings):
        """Refreshes the specific plugin and generates an updated image."""
        plugin_config = self.device_config.get_plugin(plugin_id)

        if not plugin_config:
            raise ValueError(f"Plugin '{plugin_id}' not found.")

        plugin_instance = get_plugin_instance(plugin_config)
        image = plugin_instance.generate_image(plugin_settings, self.device_config)

        return image, plugin_config.get("image_settings", [])

    def _get_current_datetime(self):
        """Retrieves the current datetime based on the device's configured timezone."""
        tz_str = self.device_config.get_config("timezone", default="UTC")
        return datetime.now(pytz.timezone(tz_str))

    def _determine_next_plugin(self, playlist_manager, latest_refresh_info, current_dt):
        """Determines the next plugin to refresh based on the active playlist, plugin cycle interval, and current time."""
        playlist = playlist_manager.determine_active_playlist(current_dt)
        if not playlist:
            playlist_manager.active_playlist = None
            logger.info(f"No active playlist determined.")
            return None, None

        playlist_manager.active_playlist = playlist.name
        if not playlist.plugins:
            logger.info(f"Active playlist '{playlist.name}' has no plugins.")
            return None, None

        latest_refresh_dt = latest_refresh_info.get_refresh_datetime()
        plugin_cycle_interval = self.device_config.get_config("plugin_cycle_interval_seconds", default=3600)
        should_refresh = PlaylistManager.should_refresh(latest_refresh_dt, plugin_cycle_interval, current_dt)

        if not should_refresh:
            latest_refresh_str = latest_refresh_dt.strftime('%Y-%m-%d %H:%M:%S') if latest_refresh_dt else "None"
            logger.info(f"Not time to update display. | latest_update: {latest_refresh_str} | plugin_cycle_interval: {plugin_cycle_interval}")
            return None, None

        plugin = playlist.get_next_plugin()
        logger.info(f"Determined next plugin. | active_playlist: {playlist.name} | plugin_instance: {plugin.name}")

        return playlist, plugin

    def _plugin_instance_refresh(self, plugin_instance, current_dt):
        """Handles the refresh of a specific plugin instance. Returns A tuple containing the plugin's updated
        image and the corresponding image settings to apply."""
        # determine if the plugin instance needs to be refreshed
        should_refresh = plugin_instance.should_refresh(current_dt)
        plugin_image_path = os.path.join(self.device_config.plugin_image_dir, plugin_instance.get_image_path())

        image, image_settings = None, []
        if should_refresh:
            # refresh plugin and save the new image
            logger.info(f"Refreshing plugin instance. | plugin_instance: '{plugin_instance.name}'")
            image, image_settings = self._refresh_plugin(plugin_instance.plugin_id, plugin_instance.settings)

            image.save(plugin_image_path)
            plugin_instance.latest_refresh_time = current_dt.isoformat()
        else:
            # read image file from latest refresh
            plugin_config = self.device_config.get_plugin(plugin_instance.plugin_id)

            logger.info(f"Not time to refresh plugin instance, using latest image. | plugin_instance: {plugin_instance.name}.")
            image = Image.open(plugin_image_path)
            image_settings = plugin_config.get("image_settings", [])
        
        return image, image_settings
