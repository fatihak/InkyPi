import logging
import threading
import time
from datetime import timedelta

logger = logging.getLogger(__name__)


class ButtonTask:
    """Watches Pimoroni Inky hardware buttons and triggers app actions."""

    DEFAULT_BUTTON_A_GPIO = 5
    DEFAULT_DEBOUNCE_SECONDS = 1.0
    POLL_TIMEOUT_SECONDS = 0.25

    def __init__(self, device_config, refresh_task):
        self.device_config = device_config
        self.refresh_task = refresh_task
        self.thread = None
        self.running = False
        self.request = None
        self.offsets = []
        self.button_a_gpio = self.DEFAULT_BUTTON_A_GPIO
        self.last_press_time = 0

    def start(self):
        """Start watching button A when button controls are enabled for Inky hardware."""
        if not self.is_enabled():
            logger.info("Button controls disabled or unsupported for this display type")
            return False

        if self.thread and self.thread.is_alive():
            return True

        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("Started Inky button task")
        return True

    def stop(self):
        """Stop watching button events."""
        self.running = False

        if self.thread and self.thread.is_alive():
            logger.info("Stopping Inky button task")
            self.thread.join(timeout=2)

        if self.thread and self.thread.is_alive():
            self._close_request()

    def is_enabled(self):
        """Return whether button controls should run for the current config."""
        if self.device_config.get_config("display_type", default="inky") != "inky":
            return False

        return True

    def _run(self):
        try:
            self.request, self.offsets = self._request_button_lines()
            while self.running:
                for event in self._read_events(self.request):
                    self._handle_button_event(event)
        except ImportError as e:
            logger.warning(f"Inky button controls unavailable; missing GPIO dependency: {e}")
        except Exception:
            logger.exception("Inky button task stopped after an unexpected error")
        finally:
            self.running = False
            self._close_request()

    def _request_button_lines(self):
        import gpiod
        import gpiodevice
        from gpiod.line import Bias, Direction, Edge

        self.button_a_gpio = int(self.device_config.get_config("button_a_gpio", default=self.DEFAULT_BUTTON_A_GPIO))
        input_settings = gpiod.LineSettings(
            direction=Direction.INPUT,
            bias=Bias.PULL_UP,
            edge_detection=Edge.FALLING,
        )

        chip = gpiodevice.find_chip_by_platform()
        offsets = [chip.line_offset_from_id(self.button_a_gpio)]
        line_config = dict.fromkeys(offsets, input_settings)
        request = chip.request_lines(consumer="inkypi-buttons", config=line_config)
        logger.info(f"Listening for Inky button A on GPIO {self.button_a_gpio}")
        return request, offsets

    def _read_events(self, request):
        if hasattr(request, "wait_edge_events"):
            if not request.wait_edge_events(timeout=timedelta(seconds=self.POLL_TIMEOUT_SECONDS)):
                return []
            return request.read_edge_events()

        time.sleep(self.POLL_TIMEOUT_SECONDS)
        return request.read_edge_events()

    def _handle_button_event(self, event):
        if not self.offsets or event.line_offset != self.offsets[0]:
            return

        now = time.monotonic()
        debounce_seconds = float(
            self.device_config.get_config("button_debounce_seconds", default=self.DEFAULT_DEBOUNCE_SECONDS)
        )
        if now - self.last_press_time < debounce_seconds:
            logger.debug("Ignoring debounced Inky button A press")
            return

        self.last_press_time = now
        logger.info(f"Inky button A pressed on GPIO {self.button_a_gpio}; cycling playlist")
        self.refresh_task.cycle_playlist_next()

    def _close_request(self):
        if self.request and hasattr(self.request, "release"):
            try:
                self.request.release()
            except Exception as e:
                logger.debug(f"Error while releasing Inky button GPIO request: {e}")
        self.request = None
