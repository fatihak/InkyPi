import importlib
import logging
import sys

from display.abstract_display import AbstractDisplay
from PIL import Image
from pathlib import Path
from plugins.plugin_registry import get_plugin_instance

logger = logging.getLogger(__name__)


def quantize_to_4_gray(image, epd_display):
    """
    Dither image down to the 4 exact gray levels a 4Gray-capable epd driver
    expects. The driver's own getbuffer_4Gray() does no dithering itself, just
    a raw truncation of each pixel's top 2 bits, so this has to be done before
    handing the image off, using the driver's own GRAY1-4 constants.
    """
    gray_levels = [epd_display.GRAY4, epd_display.GRAY3, epd_display.GRAY2, epd_display.GRAY1]
    palette_data = []
    for gray in gray_levels:
        palette_data += [gray, gray, gray]
    palette_img = Image.new('P', (1, 1))
    palette_img.putpalette(palette_data)

    gray_rgb = image.convert('L').convert('RGB')
    indexed_img = gray_rgb.quantize(palette=palette_img, dither=Image.Dither.FLOYDSTEINBERG)
    return indexed_img.convert('L')


class WaveshareDisplay(AbstractDisplay):
    """
    Handles Waveshare e-paper display dynamically based on device type.

    This class loads the appropriate display driver dynamically based on the 
    `display_type` specified in the device configuration, allowing support for 
    multiple Waveshare EPD models.  

    The module drivers are in display.waveshare_epd.
    """

    def initialize_display(self):
        
        """
        Initializes the Waveshare display device.

        Retrieves the display type from the device configuration and dynamically 
        loads the corresponding Waveshare EPD driver from display.waveshare_epd.

        Raises:
            ValueError: If `display_type` is missing or the specified module is 
                        not found.
        """
        
        logger.info("Initializing Waveshare display")

        # get the device type which should be the model number of the device.
        display_type = self.device_config.get_config("display_type")  
        logger.info(f"Loading EPD display for {display_type} display")

        if not display_type:
            raise ValueError("Waveshare driver but 'display_type' not specified in configuration.")

        # Construct module path dynamically - e.g. "display.waveshare_epd.epd7in3e"
        module_name = f"display.waveshare_epd.{display_type}" 

        # Workaround for some Waveshare drivers using 'import epdconfig' causing import errors
        epd_dir = Path(__file__).parent / "waveshare_epd"
        if str(epd_dir) not in sys.path:
            sys.path.insert(0, str(epd_dir))

        try:
            # Dynamically load module
            epd_module = importlib.import_module(module_name)  
            self.epd_display = epd_module.EPD()
            # Workaround for init functions with inconsistent casing
            self.epd_display_init = getattr(self.epd_display, "Init", getattr(self.epd_display, "init", None))

            if not callable(self.epd_display_init):
                raise AttributeError("No Init/init method found")

            if not hasattr(self.epd_display, "display") or not hasattr(self.epd_display, "getbuffer"):
                raise AttributeError("No display/getbuffer method found")

            self.epd_display_init()
        except ModuleNotFoundError:
            raise ValueError(f"Unsupported Waveshare display type: {display_type}")
        except AttributeError:
            raise ValueError(f"Display does not support required methods: {display_type}")

        # Workaround for 4Gray init functions with inconsistent casing across drivers
        self.epd_display_init_4gray = getattr(
            self.epd_display, "init_4Gray", getattr(self.epd_display, "Init_4Gray", None)
        )
        self.gray4_display = (
            callable(self.epd_display_init_4gray)
            and hasattr(self.epd_display, "getbuffer_4Gray")
            and hasattr(self.epd_display, "display_4Gray")
        )

        # update the resolution directly from the loaded device context
        if not self.device_config.get_config("resolution"):
            w, h = int(self.epd_display.width), int(self.epd_display.height)
            resolution = [w, h] if w >= h else [h, w]
            self.device_config.update_value(
                "resolution",
                resolution,
                write=True)


    def display_image(self, image, image_settings=[]):
        
        """
        Displays an image on the Waveshare display.

        The image has been processed by adjusting orientation, resizing, and converting it
        into the buffer format required for e-paper rendering.

        Args:
            image (PIL.Image): The image to be displayed.
            image_settings (list, optional): Additional settings to modify image rendering.

        Raises:
            ValueError: If no image is provided.
        """

        logger.info("Displaying image to Waveshare display.")
        if not image:
            raise ValueError(f"No image provided.")

        # Assume device was in sleep mode.
        if self.gray4_display:
            self.epd_display_init_4gray()
        else:
            self.epd_display_init()

        # Clear residual pixels before updating the image.
        self.epd_display.Clear()

        # Display the image on the WS display.
        if self.gray4_display:
            gray_image = quantize_to_4_gray(image, self.epd_display)
            self.epd_display.display_4Gray(self.epd_display.getbuffer_4Gray(gray_image))
        else:
            self.epd_display.display(self.epd_display.getbuffer(image))

        # Put device into low power mode (EPD displays maintain image when powered off)
        logger.info("Putting Waveshare display into sleep mode for power saving.")
        self.epd_display.sleep()
