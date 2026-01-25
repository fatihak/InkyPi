import logging
import threading
import pytz
from datetime import datetime
from refresh_task import PlaylistRefresh

logger = logging.getLogger(__name__)

try:
    from gpiozero import Button
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

DEFAULT_BUTTON_PINS = {
    "next": 5,
    "previous": 6,
    "refresh": 16,
    "pause": 24
}


class ButtonHandler:
    def __init__(self, device_config, refresh_task):
        self.device_config = device_config
        self.refresh_task = refresh_task
        self.buttons = {}

    def start(self):
        if not GPIO_AVAILABLE:
            logger.info("GPIO buttons not available. Skipping button handler.")
            return

        display_type = self.device_config.get_config("display_type", default="inky")
        if display_type != "inky":
            logger.info("Display type '%s' does not use GPIO buttons.", display_type)
            return

        configured_pins = self.device_config.get_config("button_pins", default={})
        button_pins = {**DEFAULT_BUTTON_PINS, **(configured_pins or {})}

        self.buttons["next"] = Button(button_pins["next"], pull_up=True, bounce_time=0.1)
        self.buttons["previous"] = Button(button_pins["previous"], pull_up=True, bounce_time=0.1)
        self.buttons["refresh"] = Button(button_pins["refresh"], pull_up=True, bounce_time=0.1)
        self.buttons["pause"] = Button(button_pins["pause"], pull_up=True, bounce_time=0.1)

        self.buttons["next"].when_pressed = lambda: self._run_async(self._handle_next)
        self.buttons["previous"].when_pressed = lambda: self._run_async(self._handle_previous)
        self.buttons["refresh"].when_pressed = lambda: self._run_async(self._handle_refresh)
        self.buttons["pause"].when_pressed = lambda: self._run_async(self._handle_pause)

        logger.info("GPIO button handler started.")

    def _run_async(self, handler):
        thread = threading.Thread(target=handler, daemon=True)
        thread.start()

    def _handle_next(self):
        self._refresh_playlist_action(next_plugin=True)

    def _handle_previous(self):
        self._refresh_playlist_action(next_plugin=False)

    def _handle_refresh(self):
        playlist_manager = self.device_config.get_playlist_manager()
        refresh_info = self.device_config.get_refresh_info()
        if refresh_info.refresh_type == "Playlist" and refresh_info.playlist and refresh_info.plugin_instance:
            playlist = playlist_manager.get_playlist(refresh_info.playlist)
            if playlist:
                plugin_instance = playlist.find_plugin(refresh_info.plugin_id, refresh_info.plugin_instance)
                if plugin_instance:
                    logger.info("Refreshing current plugin instance via button.")
                    self.refresh_task.manual_update(PlaylistRefresh(playlist, plugin_instance, force=True))
                    return

        logger.info("Falling back to next plugin refresh.")
        self._refresh_playlist_action(next_plugin=True)

    def _handle_pause(self):
        paused = self.refresh_task.toggle_pause()
        logger.info("Refresh pause toggled. paused=%s", paused)

    def _refresh_playlist_action(self, next_plugin):
        playlist_manager = self.device_config.get_playlist_manager()
        current_dt = self._get_current_datetime()
        playlist = playlist_manager.determine_active_playlist(current_dt)
        if not playlist or not playlist.plugins:
            logger.info("No active playlist available for button action.")
            return

        playlist_manager.active_playlist = playlist.name
        plugin_instance = playlist.get_next_plugin() if next_plugin else playlist.get_previous_plugin()
        logger.info(
            "Button action refresh. playlist=%s plugin_instance=%s",
            playlist.name,
            plugin_instance.name
        )
        self.refresh_task.manual_update(PlaylistRefresh(playlist, plugin_instance, force=True))

    def _get_current_datetime(self):
        tz_str = self.device_config.get_config("timezone", default="UTC")
        return datetime.now(pytz.timezone(tz_str))
