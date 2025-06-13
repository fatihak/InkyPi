class AbstractDisplay:
    """
    Abstract base class for all display devices.

    This class defines methods taht subclasses are required to implement for
    initialization and to display images on a screen.  

    These implementations will be device specific.
    """

    def __init__(self, device_config):
        """
        Initializes the display manager with the provided device configuration.

        Args:
            device_config (object): Configuration object for the display device.
        """
        self.device_config = device_config
        self.initialize_display()

    def initialize_display(self):
        """
        Abstract method to initialize the display hardware.

        This method must be implemented by subclasses to set up the display
        device properly.

        Raises:
            NotImplementedError: If not implemented in a subclass.
        """
        raise NotImplementedError("Method 'initialize_display(...) must be provided in a subclass.")

    def display_image(self, image, image_settings=[]):
        """
        Abstract method to display an image on the screen.  Implementations of this
        method should handle the device specific operations.

        Args:
            image (PIL.Image): The image to be displayed.
            image_settings (list, optional): List of settings to modify how the image is displayed.

        Raises:
            NotImplementedError: If not implemented in a subclass.
        """
        raise NotImplementedError("Method 'display_image(...) must be provided in a subclass.")
