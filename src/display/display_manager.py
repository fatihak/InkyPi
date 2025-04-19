import fnmatch
import json
import logging

from display.inky_display import InkyDisplay
from display.waveshare_display import WaveshareDisplay

logger = logging.getLogger(__name__)

class DisplayManager:
    def __init__(self, device_config):
        """Manages the display and rendering of images."""
        self.device_config = device_config

        prettyJson = json.dumps(device_config.config, indent=3)

        logger.info(f"Starting display manager with config {prettyJson}")
        
        display_type = device_config.get_config("display_type", default="inky")

        if display_type == "inky":
            self.display = InkyDisplay(device_config)
        elif fnmatch.fnmatch(display_type, "epd*in*"):  
            # derived from waveshare epd - we assume here that will be consistent
            # otherwise we will have to enshring the manufacturer in the 
            # display_type and then have a display_model parameter.  Will leave
            # that for future use if the need arises.
            self.display = WaveshareDisplay(device_config)
        else:
            raise ValueError(f"Unsupported display type: {display_type}")

    def display_image(self, image, image_settings=[]):
        """Delegate image display to the appropriate concrete instance."""
        self.display.display_image(image, image_settings)