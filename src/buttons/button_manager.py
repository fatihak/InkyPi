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
    - Execute global action (refresh, shutdown, etc.)
    - Forward to current plugin's on_button_press()
    """
    
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
    
    def _on_button_press(self, button_id: ButtonID, press_type: PressType):
        """Main button event handler.
        
        Priority order:
        1. Configured global actions (from config)
        2. Active plugin's on_button_press() 
        3. Default actions (refresh, playlist nav, shutdown)
        """
        logger.info(f"Button event: {button_id.value} {press_type.value}")
        
        # 1. Check for configured global action (highest priority)
        button_config = self._device_config.get_config("buttons", default={})
        global_actions = button_config.get("global_actions", {})
        action_key = f"{button_id.value}_{press_type.value}"
        action = global_actions.get(action_key)
        
        if action:
            self._execute_action(action)
            return
        
        # 2. Forward to plugin first (plugin can handle its own buttons)
        if self._forward_to_plugin(button_id, press_type):
            return
        
        # 3. Default actions as fallback
        default_action = self._get_default_action(button_id, press_type)
        if default_action:
            self._execute_action(default_action)
    
    def _get_default_action(self, button_id: ButtonID, press_type: PressType) -> Optional[str]:
        """Returns default action for button combination."""
        defaults = {
            (ButtonID.A, PressType.SHORT): "refresh",
            (ButtonID.B, PressType.LONG): "prev_plugin",
            (ButtonID.C, PressType.LONG): "next_plugin",
            (ButtonID.D, PressType.LONG): "shutdown",
        }
        return defaults.get((button_id, press_type))
    
    def _execute_action(self, action: str):
        """Execute a global action."""
        logger.info(f"Executing action: {action}")
        
        actions = {
            "shutdown": self._shutdown,
            "reboot": self._reboot,
            "refresh": self._refresh_display,
            "next_plugin": self._next_plugin,
            "prev_plugin": self._prev_plugin,
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
                # Trigger display refresh for the current plugin
                self._refresh_current_plugin(plugin_id, instance_name)
                return True
        
        return False
    
    def _refresh_current_plugin(self, plugin_id: str, instance_name: str):
        """Refresh the display with the current plugin after button handling."""
        from refresh_task import PlaylistRefresh
        
        playlist_manager = self._device_config.get_playlist_manager()
        refresh_info = self._device_config.get_refresh_info()
        
        # Find the playlist and plugin instance
        playlist = playlist_manager.get_playlist(refresh_info.playlist)
        if not playlist:
            logger.warning(f"Playlist not found for refresh: {refresh_info.playlist}")
            return
        
        plugin_instance = playlist.find_plugin(plugin_id, instance_name)
        if not plugin_instance:
            logger.warning(f"Plugin instance not found: {plugin_id}/{instance_name}")
            return
        
        try:
            # Use regenerate=True to force new image generation after plugin state change
            refresh_action = PlaylistRefresh(playlist, plugin_instance, regenerate=True)
            self._refresh_task.manual_update(refresh_action)
        except Exception as e:
            logger.error(f"Failed to refresh plugin '{plugin_id}': {e}")
    
    def _shutdown(self):
        logger.info("Shutting down...")
        subprocess.run(["sudo", "shutdown", "-h", "now"])
    
    def _reboot(self):
        logger.info("Rebooting...")
        subprocess.run(["sudo", "reboot"])
    
    def _refresh_display(self):
        logger.info("Manual refresh triggered by button")
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
        
        # Get current time for determining active playlist
        tz_str = self._device_config.get_config("timezone", default="UTC")
        current_dt = datetime.now(pytz.timezone(tz_str))
        
        # Find active playlist
        playlist = playlist_manager.determine_active_playlist(current_dt)
        if not playlist:
            logger.warning("No active playlist for navigation")
            return
        
        if not playlist.plugins:
            logger.warning(f"Playlist '{playlist.name}' has no plugins")
            return
        
        # Navigate to next/prev plugin
        if direction == "next":
            plugin_instance = playlist.get_next_plugin()
        else:
            plugin_instance = playlist.get_previous_plugin()
        
        if not plugin_instance:
            logger.warning("No plugin to navigate to")
            return
        
        logger.info(f"Navigating to plugin: {plugin_instance.name} (index: {playlist.current_plugin_index})")
        
        # Save updated index to config
        self._device_config.write_config()
        
        # Trigger manual update with this specific plugin
        try:
            refresh_action = PlaylistRefresh(playlist, plugin_instance, force=True)
            self._refresh_task.manual_update(refresh_action)
        except Exception as e:
            logger.error(f"Failed to display plugin '{plugin_instance.name}': {e}")
