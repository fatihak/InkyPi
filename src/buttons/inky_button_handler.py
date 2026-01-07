import logging
import time
from buttons.abstract_button_handler import (
    AbstractButtonHandler, 
    ButtonID, 
    PressType
)

logger = logging.getLogger(__name__)

# Default GPIO pins for Inky Impression buttons
# Can be overridden via device config for different models
DEFAULT_BUTTON_PINS = {
    ButtonID.A: 5,
    ButtonID.B: 6,
    ButtonID.C: 16,  # GPIO 25 on 13.3" model
    ButtonID.D: 24,
}

LONG_PRESS_THRESHOLD = 1.0  # seconds


class InkyButtonHandler(AbstractButtonHandler):
    """
    Button handler for Inky Impression hardware.
    
    Uses gpiozero library for GPIO pin access on Raspberry Pi.
    Supports both short and long press detection.
    """
    
    def __init__(self, button_pins: dict = None):
        super().__init__()
        self._button_pins = self._parse_button_pins(button_pins)
        self._buttons = {}
        self._press_times = {}
        self._long_press_fired = set()
    
    def _parse_button_pins(self, config_pins: dict) -> dict:
        """Convert config pins (string keys) to ButtonID keys."""
        if not config_pins:
            return DEFAULT_BUTTON_PINS.copy()
        
        result = {}
        for button_id in ButtonID:
            # Check both ButtonID and string key
            if button_id in config_pins:
                result[button_id] = config_pins[button_id]
            elif button_id.value in config_pins:
                result[button_id] = config_pins[button_id.value]
            else:
                # Use default if not specified
                result[button_id] = DEFAULT_BUTTON_PINS.get(button_id)
        
        return result
    
    def start(self):
        if self._running:
            return
            
        try:
            from gpiozero import Button
            
            for button_id, pin in self._button_pins.items():
                button = Button(
                    pin, 
                    pull_up=True, 
                    hold_time=LONG_PRESS_THRESHOLD,
                    bounce_time=0.05
                )
                
                # Bind events using closures to capture button_id
                button.when_pressed = self._make_pressed_handler(button_id)
                button.when_released = self._make_released_handler(button_id)
                button.when_held = self._make_held_handler(button_id)
                
                self._buttons[button_id] = button
                logger.info(f"Button {button_id.value} initialized on GPIO {pin}")
            
            self._running = True
            logger.info("InkyButtonHandler started")
            
        except ImportError:
            logger.error("gpiozero not available. Install with: pip install gpiozero")
        except Exception as e:
            logger.error(f"Failed to initialize buttons: {e}")
    
    def stop(self):
        if not self._running:
            return
            
        for button in self._buttons.values():
            button.close()
        
        self._buttons.clear()
        self._press_times.clear()
        self._long_press_fired.clear()
        self._running = False
        logger.info("InkyButtonHandler stopped")
    
    def _make_pressed_handler(self, button_id: ButtonID):
        def handler():
            self._press_times[button_id] = time.time()
            self._long_press_fired.discard(button_id)
            logger.debug(f"Button {button_id.value} pressed")
        return handler
    
    def _make_released_handler(self, button_id: ButtonID):
        def handler():
            # Skip if long press already fired
            if button_id in self._long_press_fired:
                self._long_press_fired.discard(button_id)
                return
            
            press_start = self._press_times.pop(button_id, None)
            if press_start is None:
                return
            
            duration = time.time() - press_start
            if duration < LONG_PRESS_THRESHOLD:
                logger.info(f"Button {button_id.value} short press")
                self._notify(button_id, PressType.SHORT)
        return handler
    
    def _make_held_handler(self, button_id: ButtonID):
        def handler():
            logger.info(f"Button {button_id.value} long press")
            self._long_press_fired.add(button_id)
            self._notify(button_id, PressType.LONG)
        return handler
