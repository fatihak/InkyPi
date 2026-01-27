import os
import logging
from PIL import Image, ImageOps, ImageColor

from plugins.base_plugin.base_plugin import BasePlugin
from buttons import ButtonID, PressType
from utils.image_utils import pad_image_blur

logger = logging.getLogger(__name__)

MAX_IMAGES = 10


class PhotoFrame(BasePlugin):
    """
    Photo Frame plugin - displays uploaded images with button navigation.
    
    Supports:
    - Up to 10 images per instance
    - Button B (short): previous image
    - Button C (short): next image
    """
    
    def generate_image(self, settings, device_config) -> Image:
        """Generate the current frame image."""
        images = settings.get("photos[]", [])
        
        if not images:
            return self._create_placeholder(device_config)
        
        # Get current index
        current_index = settings.get("current_index", 0)
        
        # Validate index bounds
        if current_index >= len(images) or current_index < 0:
            current_index = 0
            settings["current_index"] = current_index
        
        image_path = images[current_index]
        
        # Check if file exists
        if not os.path.exists(image_path):
            logger.warning(f"Image not found: {image_path}")
            images.remove(image_path)
            settings["photos[]"] = images
            if images:
                settings["current_index"] = 0
                return self.generate_image(settings, device_config)
            return self._create_placeholder(device_config)
        
        try:
            image = Image.open(image_path)
        except Exception as e:
            logger.error(f"Failed to open image {image_path}: {e}")
            return self._create_placeholder(device_config)
        
        # Apply padding/scaling if enabled
        if settings.get("padImage") != "false":
            dimensions = device_config.get_resolution()
            orientation = device_config.get_config("orientation")
            if orientation == "vertical":
                dimensions = dimensions[::-1]
            
            bg_option = settings.get("backgroundOption", "blur")
            if bg_option == "blur":
                image = pad_image_blur(image, dimensions)
            else:
                bg_color = settings.get("backgroundColor", "#000000")
                color = ImageColor.getcolor(bg_color, "RGB")
                image = ImageOps.pad(image, dimensions, color=color, method=Image.Resampling.LANCZOS)
        
        return image
    
    def _create_placeholder(self, device_config) -> Image:
        """Create a placeholder image when no photos are available."""
        dimensions = device_config.get_resolution()
        orientation = device_config.get_config("orientation")
        if orientation == "vertical":
            dimensions = dimensions[::-1]
        
        image = Image.new("RGB", dimensions, color=(40, 40, 40))
        return image
    
    def on_button_press(self, button_id: ButtonID, press_type: PressType, device_config) -> bool:
        """
        Handle button press for image navigation.
        
        B (short): Previous image
        C (short): Next image
        
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
        
        images = plugin_instance.settings.get("photos[]", [])
        # Filter existing files
        images = [p for p in images if os.path.exists(p)]
        
        if not images:
            return False
        
        current_index = plugin_instance.settings.get("current_index", 0)
        if current_index >= len(images):
            current_index = 0
        
        if button_id == ButtonID.B:
            current_index = (current_index - 1) % len(images)
            plugin_instance.settings["current_index"] = current_index
            device_config.write_config()
            logger.info(f"Photo Frame: previous image (index: {current_index})")
            return True
        
        elif button_id == ButtonID.C:
            current_index = (current_index + 1) % len(images)
            plugin_instance.settings["current_index"] = current_index
            device_config.write_config()
            logger.info(f"Photo Frame: next image (index: {current_index})")
            return True
        
        return False
    
    def get_button_hints(self) -> dict:
        """Return button hints for UI."""
        return {
            "B": "Previous photo",
            "C": "Next photo"
        }
    
    def cleanup(self, settings):
        """Delete all uploaded images when plugin instance is removed."""
        images = settings.get("photos[]", [])
        
        for image_path in images:
            if os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    logger.info(f"Deleted photo: {image_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete {image_path}: {e}")
