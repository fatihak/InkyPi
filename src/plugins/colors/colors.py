import json
import logging
from PIL import Image

from plugins.base_plugin.base_plugin import BasePlugin
from buttons import ButtonID, PressType

logger = logging.getLogger(__name__)

# Default color palette
DEFAULT_COLORS = [
    "#FF0000",  # Red
    "#00FF00",  # Green
    "#0000FF",  # Blue
    "#FFFF00",  # Yellow
    "#FF00FF",  # Magenta
    "#00FFFF",  # Cyan
    "#FFFFFF",  # White
    "#000000",  # Black
    "#FF8000",  # Orange
    "#8000FF",  # Purple
]


class Colors(BasePlugin):
    """
    Colors plugin - displays solid colors with button navigation.
    
    Button B (short): Previous color
    Button C (short): Next color
    """
    
    def generate_image(self, settings, device_config) -> Image:
        """Generate solid color image."""
        dimensions = device_config.get_resolution()
        orientation = device_config.get_config("orientation")
        if orientation == "vertical":
            dimensions = dimensions[::-1]
        
        # Get colors list (stored as JSON string)
        colors = self._get_colors(settings)
        
        # Get current index
        current_index = settings.get("current_index", 0)
        if current_index >= len(colors) or current_index < 0:
            current_index = 0
        
        color = colors[current_index]
        
        # Create solid color image
        image = Image.new("RGB", dimensions, color=color)
        
        return image
    
    def _get_colors(self, settings) -> list:
        """Parse colors from settings."""
        colors = settings.get("colors", None)
        if colors:
            try:
                colors = json.loads(colors) if isinstance(colors, str) else colors
            except:
                colors = DEFAULT_COLORS
        else:
            colors = DEFAULT_COLORS
        
        return colors if colors else DEFAULT_COLORS
    
    def on_button_press(self, button_id: ButtonID, press_type: PressType, device_config) -> bool:
        """
        Handle button press for color navigation.
        
        B (short): Previous color
        C (short): Next color
        
        Returns True if handled (ButtonManager will trigger refresh).
        """
        if press_type != PressType.SHORT:
            return False
        
        if button_id not in (ButtonID.B, ButtonID.C):
            return False
        
        # Get current plugin instance from refresh_info
        refresh_info = device_config.get_refresh_info()
        if refresh_info.plugin_id != self.get_plugin_id():
            return False
        
        instance_name = refresh_info.plugin_instance
        if not instance_name:
            return False
        
        # Find the plugin instance in playlist
        playlist_manager = device_config.get_playlist_manager()
        plugin_instance = playlist_manager.find_plugin(self.get_plugin_id(), instance_name)
        
        if not plugin_instance:
            return False
        
        colors = self._get_colors(plugin_instance.settings)
        
        current_index = plugin_instance.settings.get("current_index", 0)
        if current_index >= len(colors):
            current_index = 0
        
        if button_id == ButtonID.B:
            current_index = (current_index - 1) % len(colors)
            plugin_instance.settings["current_index"] = current_index
            device_config.write_config()
            logger.info(f"Colors: previous color (index: {current_index}, color: {colors[current_index]})")
            return True
        
        elif button_id == ButtonID.C:
            current_index = (current_index + 1) % len(colors)
            plugin_instance.settings["current_index"] = current_index
            device_config.write_config()
            logger.info(f"Colors: next color (index: {current_index}, color: {colors[current_index]})")
            return True
        
        return False
    
    def get_button_hints(self) -> dict:
        """Return button hints for UI."""
        return {
            "B": "Previous color",
            "C": "Next color"
        }
