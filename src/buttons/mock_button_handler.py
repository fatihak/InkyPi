import logging
import threading
from buttons.abstract_button_handler import (
    AbstractButtonHandler, 
    ButtonID, 
    PressType
)

logger = logging.getLogger(__name__)


class MockButtonHandler(AbstractButtonHandler):
    """
    Mock button handler for development without hardware.
    
    Allows simulating button presses via:
    - Web UI buttons
    - API endpoint (/simulate_button)
    """
    
    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
    
    def start(self):
        self._running = True
        logger.info("MockButtonHandler started (dev mode)")
    
    def stop(self):
        self._running = False
        logger.info("MockButtonHandler stopped")
    
    def simulate_press(self, button_id: ButtonID, press_type: PressType):
        """
        Simulate a button press. Called from web UI or API.
        
        Args:
            button_id: Which button was pressed (A, B, C, D)
            press_type: Press type (short, long)
        """
        if not self._running:
            logger.warning("MockButtonHandler not running, ignoring simulate_press")
            return
        
        logger.info(f"Simulated button {button_id.value} {press_type.value} press")
        with self._lock:
            self._notify(button_id, press_type)
