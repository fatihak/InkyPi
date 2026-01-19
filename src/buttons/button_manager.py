import logging
import subprocess
from typing import TYPE_CHECKING, Optional
from buttons.abstract_button_handler import AbstractButtonHandler, ButtonID, PressType

if TYPE_CHECKING:
    from refresh_task import RefreshTask
    from config import Config

logger = logging.getLogger(__name__)


class ButtonManager:
    """
    Manages button events and maps them to actions.
    
    Receives events from ButtonHandler, decides what to do:
    - Forward to current plugin's on_button_press() (plugins have priority)
    - Execute configured action from settings
    - Fall back to default actions
    """
    
    # Default actions when nothing is configured
    DEFAULT_ACTIONS = {
        ("A", "short"): "refresh",
        ("B", "long"): "prev_plugin",
        ("C", "long"): "next_plugin",
        ("D", "long"): "shutdown",
    }
    
    def __init__(
        self, 
        button_handler: AbstractButtonHandler,
        refresh_task: "RefreshTask",
        device_config: "Config"
    ):
        self._handler = button_handler
        self._refresh_task = refresh_task
        self._device_config = device_config
        self._handler.set_callback(self._on_button_press)
    
    def start(self):
        self._handler.start()
        logger.info("ButtonManager started")
    
    def stop(self):
        self._handler.stop()
        logger.info("ButtonManager stopped")
    
    @property
    def handler(self) -> AbstractButtonHandler:
        return self._handler
    
    @classmethod
    def get_default_action(cls, button: str, press_type: str) -> Optional[str]:
        """Get the default action for a button/press_type combination."""
        return cls.DEFAULT_ACTIONS.get((button, press_type))
    
    def _on_button_press(self, button_id: ButtonID, press_type: PressType):
        """Main button event handler.
        
        Priority order:
        1. Plugin's on_button_press() - plugins get first chance
        2. Configured actions from settings (button_actions)
        3. Default actions as fallback
        """
        logger.info(f"Button event: {button_id.value} {press_type.value}")
        
        action_key = f"{button_id.value}_{press_type.value}"
        
        # Get configured action
        button_actions = self._device_config.get_config("button_actions", default={})
        configured_action = button_actions.get(action_key)
        
        # If action is explicitly "none", do nothing
        if configured_action == "none":
            logger.debug(f"Action disabled for {action_key}")
            return
        
        # 1. Try plugin first (plugins have priority)
        if self._forward_to_plugin(button_id, press_type):
            return
        
        # 2. Use configured action if set, otherwise fall back to default
        action = configured_action or self.DEFAULT_ACTIONS.get((button_id.value, press_type.value))
        
        if action:
            self._execute_action(action)
    
    def _execute_action(self, action: str):
        """Execute a button action."""
        logger.info(f"Executing action: {action}")
        
        actions = {
            "shutdown": self._shutdown,
            "reboot": self._reboot,
            "refresh": self._refresh_display,
            "refresh_regenerate": self._refresh_regenerate,
            "next_plugin": self._next_plugin,
            "prev_plugin": self._prev_plugin,
            "next_playlist": self._next_playlist,
            "none": lambda: None,
        }
        
        handler = actions.get(action)
        if handler:
            handler()
        else:
            logger.warning(f"Unknown action: {action}")
    
    def _forward_to_plugin(self, button_id: ButtonID, press_type: PressType) -> bool:
        """Forward button event to the current active plugin.
        
        Returns:
            True if plugin handled the event, False otherwise.
        """
        refresh_info = self._device_config.get_refresh_info()
        plugin_id = refresh_info.plugin_id
        instance_name = refresh_info.plugin_instance
        
        if not plugin_id:
            logger.debug("No active plugin to forward button event")
            return False
        
        plugin_config = self._device_config.get_plugin(plugin_id)
        if not plugin_config:
            logger.debug(f"Plugin config not found for {plugin_id}")
            return False
        
        from plugins.plugin_registry import get_plugin_instance
        plugin = get_plugin_instance(plugin_config)
        
        if hasattr(plugin, 'on_button_press'):
            handled = plugin.on_button_press(button_id, press_type, self._device_config)
            if handled:
                logger.debug(f"Button event handled by plugin {plugin_id}")
                self._refresh_current_plugin(plugin_id, instance_name)
                return True
        
        return False
    
    def _refresh_current_plugin(self, plugin_id: str, instance_name: str):
        """Refresh the display with the current plugin after button handling."""
        from refresh_task import PlaylistRefresh
        
        playlist_manager = self._device_config.get_playlist_manager()
        refresh_info = self._device_config.get_refresh_info()
        
        playlist = playlist_manager.get_playlist(refresh_info.playlist)
        if not playlist:
            logger.warning(f"Playlist not found for refresh: {refresh_info.playlist}")
            return
        
        plugin_instance = playlist.find_plugin(plugin_id, instance_name)
        if not plugin_instance:
            logger.warning(f"Plugin instance not found: {plugin_id}/{instance_name}")
            return
        
        try:
            refresh_action = PlaylistRefresh(playlist, plugin_instance, regenerate=True)
            self._refresh_task.manual_update(refresh_action)
        except Exception as e:
            logger.error(f"Failed to refresh plugin '{plugin_id}': {e}")
    
    # ========== Action Handlers ==========
    
    def _shutdown(self):
        """Shutdown the system."""
        logger.info("Shutting down...")
        subprocess.run(["sudo", "shutdown", "-h", "now"])
    
    def _reboot(self):
        """Reboot the system."""
        logger.info("Rebooting...")
        subprocess.run(["sudo", "reboot"])
    
    def _refresh_display(self):
        """Refresh display with current plugin (use cached image if available)."""
        logger.info("Manual refresh triggered by button")
        self._refresh_task.signal_config_change()
    
    def _refresh_regenerate(self):
        """Force regenerate image for current plugin."""
        logger.info("Force regenerate triggered by button")
        refresh_info = self._device_config.get_refresh_info()
        plugin_id = refresh_info.plugin_id
        instance_name = refresh_info.plugin_instance
        
        if plugin_id:
            self._refresh_current_plugin(plugin_id, instance_name)
        else:
            self._refresh_task.signal_config_change()
    
    def _next_plugin(self):
        """Switch to next plugin in playlist."""
        logger.info("Next plugin requested")
        self._navigate_playlist(direction="next")
    
    def _prev_plugin(self):
        """Switch to previous plugin in playlist."""
        logger.info("Previous plugin requested")
        self._navigate_playlist(direction="prev")
    
    def _navigate_playlist(self, direction: str):
        """Navigate through playlist and trigger display update."""
        from datetime import datetime
        import pytz
        from refresh_task import PlaylistRefresh
        
        playlist_manager = self._device_config.get_playlist_manager()
        
        tz_str = self._device_config.get_config("timezone", default="UTC")
        current_dt = datetime.now(pytz.timezone(tz_str))
        
        playlist = playlist_manager.determine_active_playlist(current_dt)
        if not playlist:
            logger.warning("No active playlist for navigation")
            return
        
        if not playlist.plugins:
            logger.warning(f"Playlist '{playlist.name}' has no plugins")
            return
        
        if direction == "next":
            plugin_instance = playlist.get_next_plugin()
        else:
            plugin_instance = playlist.get_previous_plugin()
        
        if not plugin_instance:
            logger.warning("No plugin to navigate to")
            return
        
        logger.info(f"Navigating to plugin: {plugin_instance.name} (index: {playlist.current_plugin_index})")
        
        self._device_config.write_config()
        
        try:
            refresh_action = PlaylistRefresh(playlist, plugin_instance, force=True)
            self._refresh_task.manual_update(refresh_action)
        except Exception as e:
            logger.error(f"Failed to display plugin '{plugin_instance.name}': {e}")
    
    def _next_playlist(self):
        """Switch to next playlist."""
        logger.info("Next playlist requested")
        playlist_manager = self._device_config.get_playlist_manager()
        playlists = playlist_manager.playlists
        
        if len(playlists) <= 1:
            logger.info("Only one playlist available")
            return
        
        current_name = playlist_manager.active_playlist
        playlist_names = [p.name for p in playlists]
        
        try:
            current_idx = playlist_names.index(current_name)
            next_idx = (current_idx + 1) % len(playlist_names)
            next_name = playlist_names[next_idx]
        except ValueError:
            next_name = playlist_names[0]
        
        playlist_manager.active_playlist = next_name
        self._device_config.write_config()
        
        logger.info(f"Switched to playlist: {next_name}")
        self._refresh_task.signal_config_change()
