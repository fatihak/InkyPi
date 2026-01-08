import logging
import time
import threading
from buttons.abstract_button_handler import (
    AbstractButtonHandler, 
    ButtonID, 
    PressType
)

logger = logging.getLogger(__name__)

# Default GPIO pins for Inky Impression buttons
DEFAULT_BUTTON_PINS = {
    ButtonID.A: 5,
    ButtonID.B: 6,
    ButtonID.C: 16,
    ButtonID.D: 24,
}

LONG_PRESS_THRESHOLD = 1.0  # seconds
DOUBLE_CLICK_THRESHOLD = 0.4  # seconds between clicks


class InkyButtonHandler(AbstractButtonHandler):
    """
    Button handler for Inky Impression hardware.
    
    Uses gpiozero library for GPIO pin access on Raspberry Pi.
    Supports short, double, and long press detection.
    """
    
    def __init__(self, button_pins: dict = None):
        super().__init__()
        self._button_pins = self._parse_button_pins(button_pins)
        self._buttons = {}
        self._press_times = {}
        self._long_press_fired = set()
        self._click_counts = {}
        self._click_timers = {}
    
    def _parse_button_pins(self, config_pins: dict) -> dict:
        """Convert config pins (string keys) to ButtonID keys."""
        if not config_pins:
            return DEFAULT_BUTTON_PINS.copy()
        
        result = {}
        for button_id in ButtonID:
            if button_id in config_pins:
                result[button_id] = config_pins[button_id]
            elif button_id.value in config_pins:
                result[button_id] = config_pins[button_id.value]
            else:
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
                
                button.when_pressed = self._make_pressed_handler(button_id)
                button.when_released = self._make_released_handler(button_id)
                button.when_held = self._make_held_handler(button_id)
                
                self._buttons[button_id] = button
                self._click_counts[button_id] = 0
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
        
        # Cancel any pending timers
        for timer in self._click_timers.values():
            timer.cancel()
        
        for button in self._buttons.values():
            button.close()
        
        self._buttons.clear()
        self._press_times.clear()
        self._long_press_fired.clear()
        self._click_counts.clear()
        self._click_timers.clear()
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
                # This is a click - check for double click
                self._handle_click(button_id)
        return handler
    
    def _handle_click(self, button_id: ButtonID):
        """Handle click and detect single vs double click."""
        # Cancel existing timer if any
        if button_id in self._click_timers:
            self._click_timers[button_id].cancel()
        
        self._click_counts[button_id] = self._click_counts.get(button_id, 0) + 1
        
        if self._click_counts[button_id] == 2:
            # Double click detected
            logger.info(f"Button {button_id.value} double press")
            self._click_counts[button_id] = 0
            self._notify(button_id, PressType.DOUBLE)
        else:
            # Wait for potential second click
            timer = threading.Timer(
                DOUBLE_CLICK_THRESHOLD,
                self._single_click_timeout,
                args=[button_id]
            )
            self._click_timers[button_id] = timer
            timer.start()
    
    def _single_click_timeout(self, button_id: ButtonID):
        """Called when double-click window expires - fire single click."""
        if self._click_counts.get(button_id, 0) == 1:
            logger.info(f"Button {button_id.value} short press")
            self._click_counts[button_id] = 0
            self._notify(button_id, PressType.SHORT)
    
    def _make_held_handler(self, button_id: ButtonID):
        def handler():
            # Cancel double-click detection on long press
            if button_id in self._click_timers:
                self._click_timers[button_id].cancel()
            self._click_counts[button_id] = 0
            
            logger.info(f"Button {button_id.value} long press")
            self._long_press_fired.add(button_id)
            self._notify(button_id, PressType.LONG)
        return handler
