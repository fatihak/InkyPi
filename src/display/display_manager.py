import fnmatch
import json
import logging

from utils.image_utils import change_orientation
from utils.image_loader import AdaptiveImageLoader
from display.mock_display import MockDisplay

logger = logging.getLogger(__name__)

# Try to import hardware displays, but don't fail if they're not available
try:
    from display.inky_display import InkyDisplay
except ImportError:
    logger.info("Inky display not available, hardware support disabled")

try:
    from display.waveshare_display import WaveshareDisplay
except ImportError:
    logger.info("Waveshare display not available, hardware support disabled")


class DisplayManager:
    """Manages the display and rendering of images."""

    def __init__(self, device_config):
        """
        Initializes the display manager and selects the correct display type 
        based on the configuration.

        Args:
            device_config (object): Configuration object containing display settings.

        Raises:
            ValueError: If an unsupported display type is specified.
        """
        self.device_config = device_config
     
        display_type = device_config.get_config("display_type", default="inky")

        if display_type == "mock":
            self.display = MockDisplay(device_config)
        elif display_type == "inky":
            self.display = InkyDisplay(device_config)
        elif fnmatch.fnmatch(display_type, "epd*in*"):  
            # derived from waveshare epd - we assume here that will be consistent
            # otherwise we will have to enshring the manufacturer in the 
            # display_type and then have a display_model parameter.  Will leave
            # that for future use if the need arises.
            #
            # see https://github.com/waveshareteam/e-Paper
            self.display = WaveshareDisplay(device_config)
        else:
            raise ValueError(f"Unsupported display type: {display_type}")

    def display_image(self, image, image_settings=[]):
        """
        Delegates image rendering to the appropriate display instance.

        Args:
            image (PIL.Image): The image to be displayed.
            image_settings (list, optional): List of settings to modify image rendering.

        Raises:
            ValueError: If no valid display instance is found.
        """
        if not hasattr(self, "display"):
            raise ValueError("No valid display instance initialized.")
        
        # Save the image
        logger.info(f"Saving image to {self.device_config.current_image_file}")
        image.save(self.device_config.current_image_file)

        # Adjust specific orientation (e.g., vertical/horizontal rotations)
        image = change_orientation(image, self.device_config.get_config("orientation"))
        
        if self.device_config.get_config("inverted_image"): 
            image = image.rotate(180)

        # Route through the hardware-aware image loader
        # Pass the config so the loader can read the JSON override
        processor = AdaptiveImageLoader(self.device_config)
        resolution = self.device_config.get_resolution()
        
        # ONLY process if the image hasn't already been quantized by a plugin
        if image.mode != "P":
            logger.info("Image not yet optimized for Spectra 6. Processing now...")
            calculated_type = processor._detect_content_type(image)
            image = processor._process_and_resize(
                img=image, 
                dimensions=resolution, 
                original_size=image.size,
                content_type=calculated_type
            )
        else:
            logger.info("Image already optimized (Palette mode). Skipping duplicate processing.")

        # Pass to the concrete instance to render to the device.
        self.display.display_image(image, image_settings)
