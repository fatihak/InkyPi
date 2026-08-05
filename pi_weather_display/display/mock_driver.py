import logging

logger = logging.getLogger(__name__)


class MockDriver:
    """Saves the rendered image to a file instead of driving real hardware -
    for local (Windows) development, mirroring src/display/mock_display.py."""

    def __init__(self, output_path: str):
        self.output_path = output_path

    def show(self, image):
        image.save(self.output_path)
        logger.info(f"Saved mock render to {self.output_path}")
