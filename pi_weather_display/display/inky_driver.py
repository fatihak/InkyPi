import logging

logger = logging.getLogger(__name__)


class InkyDriver:
    """Thin wrapper around Pimoroni's inky library - same driver InkyPi already
    uses in src/display/inky_display.py, just without the Flask/device-config
    plumbing since this is a standalone single-purpose renderer."""

    def __init__(self, saturation: float = 0.5):
        from inky.auto import auto
        self.saturation = saturation
        self.inky_display = auto()
        self.inky_display.set_border(self.inky_display.BLACK)

    def show(self, image):
        logger.info("Displaying image to Inky display.")
        self.inky_display.set_image(image, saturation=self.saturation)
        self.inky_display.show()
