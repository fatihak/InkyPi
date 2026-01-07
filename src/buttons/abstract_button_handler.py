from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable, Optional


class ButtonID(Enum):
    """Button identifiers on Inky Impression display."""
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class PressType(Enum):
    """Button press type."""
    SHORT = "short"  # < 1 second
    LONG = "long"    # >= 1 second


# Callback type: function receives (button_id, press_type)
ButtonCallback = Callable[[ButtonID, PressType], None]


class AbstractButtonHandler(ABC):
    """
    Abstract base class for button handling.
    
    Subclasses must implement start() and stop() methods
    for their specific hardware or mock implementation.
    """
    
    def __init__(self):
        self._callback: Optional[ButtonCallback] = None
        self._running = False
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    def set_callback(self, callback: ButtonCallback):
        """Set the callback function for button press events."""
        self._callback = callback
    
    @abstractmethod
    def start(self):
        """Start listening for button presses."""
        pass
    
    @abstractmethod
    def stop(self):
        """Stop listening and release resources."""
        pass
    
    def _notify(self, button_id: ButtonID, press_type: PressType):
        """Invoke callback when button is pressed."""
        if self._callback:
            self._callback(button_id, press_type)
