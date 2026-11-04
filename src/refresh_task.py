import threading
import time
import os
import logging
import psutil
import pytz
from datetime import datetime, timezone
from plugins.plugin_registry import get_plugin_instance
from utils.image_utils import compute_image_hash
from model import RefreshInfo, PlaylistManager
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

class RefreshTask:
    """Handles the logic for refreshing the display using a background thread."""

    def __init__(self, device_config, display_manager):
        self.device_config = device_config
        self.display_manager = display_manager

        self.thread = None
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.running = False
        self.manual_update_request = ()

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

        This function runs in a loop, sleeping for a configured duration (`plugin_cycle_interval_seconds`) or until
        manually triggered via `manual_update()`. Determines the next plugin to refresh based on active playlists and
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
                    sleep_time = self.device_config.get_config("plugin_cycle_interval_seconds", default=60*60)

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

                    refresh_action = None
                    if self.manual_update_request:
                        # handle immediate update request
                        logger.info("Manual update requested")
                        refresh_action = self.manual_update_request
                        self.manual_update_request = ()
                    else:

                        if self.device_config.get_config("log_system_stats"):
                            self.log_system_stats()

                        # handle refresh based on playlists
                        logger.info(f"Running interval refresh check. | current_time: {current_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                        playlist, plugin_instance = self._determine_next_plugin(playlist_manager, latest_refresh, current_dt)
                        if plugin_instance:
                            refresh_action = PlaylistRefresh(playlist, plugin_instance)

                    if refresh_action:
                        skipped_plugins = False
                        if isinstance(refresh_action, PlaylistRefresh):
                            if refresh_action.force:
                                refresh_action, skipped_plugins = self._get_forced_playlist_refresh(refresh_action, current_dt)
                            else:
                                refresh_action, skipped_plugins = self._get_displayable_playlist_refresh(refresh_action, current_dt)

                        if not refresh_action:
                            if skipped_plugins:
                                self.device_config.write_config()
                            continue

                        plugin_config = self.device_config.get_plugin(refresh_action.get_plugin_id())
                        if plugin_config is None:
                            logger.error(f"Plugin config not found for '{refresh_action.get_plugin_id()}'.")
                            continue
                        plugin = get_plugin_instance(plugin_config)
                        image = refresh_action.execute(plugin, self.device_config, current_dt)
                        image_hash = compute_image_hash(image)

                        refresh_info = refresh_action.get_refresh_info()
                        refresh_info.update({"refresh_time": current_dt.isoformat(), "image_hash": image_hash})
                        # check if image is the same as current image
                        if image_hash != latest_refresh.image_hash:
                            logger.info(f"Updating display. | refresh_info: {refresh_info}")
                            self.display_manager.display_image(image, image_settings=plugin.config.get("image_settings", []))
                        else:
                            logger.info(f"Image already displayed, skipping refresh. | refresh_info: {refresh_info}")

                        # update latest refresh data in the device config
                        self.device_config.refresh_info = RefreshInfo(**refresh_info)
                        self.device_config.write_config()

            except Exception as e:
                logger.exception('Exception during refresh')
                self.refresh_result["exception"] = e  # Capture exception
            finally:
                self.refresh_event.set()

    def manual_update(self, refresh_action):
        """Manually triggers an update for the specified plugin id and plugin settings by notifying the background process."""
        if self.running:
            with self.condition:
                self.manual_update_request = refresh_action
                self.refresh_result = {}
                self.refresh_event.clear()

                self.condition.notify_all()  # Wake the thread to process manual update

            self.refresh_event.wait()
            if self.refresh_result.get("exception"):
                raise self.refresh_result.get("exception")
        else:
            logger.warning("Background refresh task is not running, unable to do a manual update")

    def signal_config_change(self):
        """Notify the background thread that config has changed (e.g., interval updated)."""
        if self.running:
            with self.condition:
                self.condition.notify_all()

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

    def _get_displayable_playlist_refresh(self, refresh_action, current_dt):
        """Returns the next playlist refresh action whose plugin does not self-skip."""
        playlist = refresh_action.playlist
        skipped_plugins = False

        for _ in range(len(playlist.plugins)):
            plugin_config = self.device_config.get_plugin(refresh_action.get_plugin_id())
            if plugin_config is None:
                logger.error(f"Plugin config not found for '{refresh_action.get_plugin_id()}'.")
                return None, skipped_plugins

            plugin = get_plugin_instance(plugin_config)
            skip_reason = plugin.skip_display_condition(refresh_action.plugin_instance.settings, self.device_config, current_dt)
            if skip_reason is None:
                return refresh_action, skipped_plugins

            skipped_plugins = True
            logger.info(
                f"Plugin skipped display. | plugin_instance: {refresh_action.plugin_instance.name} | reason: {skip_reason}"
            )
            refresh_action.save_skip_image(self.device_config, current_dt, skip_reason)
            next_plugin = playlist.get_next_plugin()
            refresh_action = PlaylistRefresh(playlist, next_plugin)

        logger.info(f"All plugins skipped display. | active_playlist: {playlist.name}")
        return None, skipped_plugins

    def _get_forced_playlist_refresh(self, refresh_action, current_dt):
        """Returns a forced playlist refresh unless that plugin self-skips."""
        plugin_config = self.device_config.get_plugin(refresh_action.get_plugin_id())
        if plugin_config is None:
            logger.error(f"Plugin config not found for '{refresh_action.get_plugin_id()}'.")
            return None, False

        plugin = get_plugin_instance(plugin_config)
        skip_reason = plugin.skip_display_condition(refresh_action.plugin_instance.settings, self.device_config, current_dt)
        if skip_reason is None:
            return refresh_action, False

        logger.info(
            f"Plugin skipped forced display. | plugin_instance: {refresh_action.plugin_instance.name} | reason: {skip_reason}"
        )
        refresh_action.save_skip_image(self.device_config, current_dt, skip_reason)
        return None, True
    
    def log_system_stats(self):
        metrics = {
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('/').percent,
            'load_avg_1_5_15': os.getloadavg(),
            'swap_percent': psutil.swap_memory().percent,
            'net_io': {
                'bytes_sent': psutil.net_io_counters().bytes_sent,
                'bytes_recv': psutil.net_io_counters().bytes_recv
            }
        }

        logger.info(f"System Stats: {metrics}")

class RefreshAction:
    """Base class for a refresh action. Subclasses should override the methods below."""
    
    def refresh(self, plugin, device_config, current_dt):
        """Perform a refresh operation and return the updated image."""
        raise NotImplementedError("Subclasses must implement the refresh method.")
    
    def get_refresh_info(self):
        """Return refresh metadata as a dictionary."""
        raise NotImplementedError("Subclasses must implement the get_refresh_info method.")
    
    def get_plugin_id(self):
        """Return the plugin ID associated with this refresh."""
        raise NotImplementedError("Subclasses must implement the get_plugin_id method.")

class ManualRefresh(RefreshAction):
    """Performs a manual refresh based on a plugin's ID and its associated settings.
    
    Attributes:
        plugin_id (str): The ID of the plugin to refresh.
        plugin_settings (dict): The settings for the manual refresh.
    """

    def __init__(self, plugin_id: str, plugin_settings: dict):
        self.plugin_id = plugin_id
        self.plugin_settings = plugin_settings

    def execute(self, plugin, device_config, current_dt: datetime):
        """Performs a manual refresh using the stored plugin ID and settings."""
        return plugin.generate_image(self.plugin_settings, device_config)

    def get_refresh_info(self):
        """Return refresh metadata as a dictionary."""
        return {"refresh_type": "Manual Update", "plugin_id": self.plugin_id}

    def get_plugin_id(self):
        """Return the plugin ID associated with this refresh."""
        return self.plugin_id

class PlaylistRefresh(RefreshAction):
    """Performs a refresh using a plugin instance within a playlist context.

    Attributes:
        playlist: The playlist object associated with the refresh.
        plugin_instance: The plugin instance to refresh.
    """

    def __init__(self, playlist, plugin_instance, force=False):
        self.playlist = playlist
        self.plugin_instance = plugin_instance
        self.force = force

    def get_refresh_info(self):
        """Return refresh metadata as a dictionary."""
        return {
            "refresh_type": "Playlist",
            "playlist": self.playlist.name,
            "plugin_id": self.plugin_instance.plugin_id,
            "plugin_instance": self.plugin_instance.name
        }

    def get_plugin_id(self):
        """Return the plugin ID associated with this refresh."""
        return self.plugin_instance.plugin_id

    def execute(self, plugin, device_config, current_dt: datetime):
        """Performs a refresh for the specified plugin instance within its playlist context."""
        # Determine the file path for the plugin's image
        plugin_image_path = os.path.join(device_config.plugin_image_dir, self.plugin_instance.get_image_path())
        has_skip_preview = self.plugin_instance.settings.get("_inkypi_skip_preview", False)

        # Check if a refresh is needed based on the plugin instance's criteria
        if self.plugin_instance.should_refresh(current_dt) or self.force or has_skip_preview:
            logger.info(f"Refreshing plugin instance. | plugin_instance: '{self.plugin_instance.name}'") 
            # Generate a new image
            image = plugin.generate_image(self.plugin_instance.settings, device_config)
            image.save(plugin_image_path)
            self.plugin_instance.settings.pop("_inkypi_skip_preview", None)
            self.plugin_instance.latest_refresh_time = current_dt.isoformat()
        else:
            logger.info(f"Not time to refresh plugin instance, using latest image. | plugin_instance: {self.plugin_instance.name}.")
            # Load the existing image from disk
            with Image.open(plugin_image_path) as img:
                image = img.copy()

        return image

    def save_skip_image(self, device_config, current_dt, reason):
        """Save a diagnostic image explaining why this plugin skipped display."""
        plugin_image_path = os.path.join(device_config.plugin_image_dir, self.plugin_instance.get_image_path())
        image = self._generate_skip_image(device_config, reason)
        image.save(plugin_image_path)

        # The skipped preview replaces the cached plugin image. Mark it so the
        # next non-skipped cycle renders fresh content instead of displaying it.
        self.plugin_instance.settings["_inkypi_skip_preview"] = True
        self.plugin_instance.latest_refresh_time = current_dt.isoformat()

    def _generate_skip_image(self, device_config, reason):
        dimensions = device_config.get_resolution()
        width, height = dimensions
        image = Image.new("RGB", dimensions, "white")
        draw = ImageDraw.Draw(image)

        title_font = self._load_skip_image_font(max(14, min(width, height) // 10), bold=True)
        subtitle_font = self._load_skip_image_font(max(12, min(width, height) // 12), bold=True)
        body_font = self._load_skip_image_font(max(10, min(width, height) // 16))
        label_font = self._load_skip_image_font(max(10, min(width, height) // 16), bold=True)

        margin = max(8, min(width, height) // 12)
        max_text_width = width - (margin * 2)
        lines = [
            (f"Plugin: {self.plugin_instance.name}", title_font),
            ("Skipped Display", subtitle_font),
        ]
        if reason:
            lines.append(("Reason:", label_font))
            for line in self._wrap_skip_image_text(draw, str(reason), body_font, max_text_width):
                lines.append((line, body_font))

        line_spacing = max(2, height // 40)
        line_heights = []
        for text, font in lines:
            bbox = draw.textbbox((0, 0), text, font=font)
            line_heights.append(bbox[3] - bbox[1])

        total_height = sum(line_heights) + (line_spacing * (len(lines) - 1))
        y = max(margin, (height - total_height) // 2)

        for index, (text, font) in enumerate(lines):
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            x = max(margin, (width - text_width) // 2)
            draw.text((x, y), text, fill="black", font=font)
            y += line_heights[index] + line_spacing

        return image

    def _load_skip_image_font(self, size, bold=False):
        font_name = "Jost-SemiBold.ttf" if bold else "Jost.ttf"
        font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "fonts", font_name)
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            return ImageFont.load_default()

    def _wrap_skip_image_text(self, draw, text, font, max_width):
        lines = []
        for paragraph in text.splitlines() or [""]:
            words = paragraph.split()
            if not words:
                lines.append("")
                continue

            current_line = words[0]
            for word in words[1:]:
                candidate = f"{current_line} {word}"
                if draw.textlength(candidate, font=font) <= max_width:
                    current_line = candidate
                else:
                    lines.append(current_line)
                    current_line = word
            lines.append(current_line)

        return lines
