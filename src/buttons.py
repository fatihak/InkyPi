"""Physical button support for the Pimoroni Inky Impression.

The four buttons on the back of the Inky Impression (A-D, top to bottom) cycle
through the active playlist:

    A  next plugin in the playlist
    B  previous plugin
    C  refresh the current plugin (fetches new data)
    D  jump to the first plugin in the playlist

Behaviour can be changed in device.json (restart InkyPi afterwards):

    "buttons_enabled": true,                 # default: on when display_type is "inky"
    "button_actions": {"A": "next", "B": "previous", "C": "refresh", "D": "first"},
    "button_pins":    {"A": 5, "B": 6, "C": 16, "D": 24}

Available actions: "next", "previous", "refresh", "first", "none".
The buttons pull the pin to ground when pressed (active low). Pins follow
Pimoroni's own buttons example (5, 6, 16, 24). If one button does nothing on
your board, check its pin on pinout.xyz and override it in "button_pins"
(e.g. {"C": 25}).
"""

import logging
import os
import threading
import time
from datetime import timedelta

from refresh_task import PlaylistRefresh

logger = logging.getLogger(__name__)

DEFAULT_PINS = {"A": 5, "B": 6, "C": 16, "D": 24}
DEFAULT_ACTIONS = {"A": "next", "B": "previous", "C": "refresh", "D": "first"}
ACTIONS = ("next", "previous", "refresh", "first", "none")
DEBOUNCE_S = 0.3


class ButtonHandler:
    def __init__(self, device_config, refresh_task):
        self.device_config = device_config
        self.refresh_task = refresh_task

        pins = dict(DEFAULT_PINS)
        pins.update({k.upper(): int(v) for k, v in (device_config.get_config("button_pins", default=None) or {}).items()})
        actions = dict(DEFAULT_ACTIONS)
        actions.update({k.upper(): str(v).lower() for k, v in (device_config.get_config("button_actions", default=None) or {}).items()})
        for name, action in list(actions.items()):
            if action not in ACTIONS:
                logger.warning(f"Unknown action '{action}' for button {name}; ignoring that button.")
                actions[name] = "none"

        self.pins = {name: pin for name, pin in pins.items() if actions.get(name, "none") != "none"}
        self.actions = actions
        self.busy = threading.Lock()
        self.last_press = 0.0
        self.thread = None

    # -- lifecycle -------------------------------------------------------------
    def start(self):
        if not self.pins:
            logger.info("All buttons are set to 'none'; button handler not started.")
            return
        self.thread = threading.Thread(target=self._run, name="buttons", daemon=True)
        self.thread.start()

    def _run(self):
        try:
            self._run_gpiod()
            return
        except ImportError:
            logger.info("gpiod not available, trying gpiozero for buttons.")
        except Exception:
            logger.exception("Button handler (gpiod) failed; trying gpiozero.")
        try:
            self._run_gpiozero()
        except ImportError:
            logger.error("No GPIO library available (gpiod or gpiozero); buttons disabled.")
        except Exception:
            logger.exception("Button handler (gpiozero) failed; buttons disabled.")

    def _run_gpiod(self):
        # Same approach as Pimoroni's own Inky buttons example (gpiod v2 +
        # gpiodevice, both installed with the inky library).
        import gpiod
        import gpiodevice
        from gpiod.line import Bias, Direction, Edge

        chip = gpiodevice.find_chip_by_platform()
        settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP,
                                      edge_detection=Edge.FALLING,
                                      debounce_period=timedelta(milliseconds=20))
        offsets = {chip.line_offset_from_id(pin): name for name, pin in self.pins.items()}
        try:
            request = chip.request_lines(consumer="inkypi-buttons", config=dict.fromkeys(offsets, settings))
        except OSError:
            # some kernels reject hardware debounce; software debounce still applies
            settings = gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP,
                                          edge_detection=Edge.FALLING)
            request = chip.request_lines(consumer="inkypi-buttons", config=dict.fromkeys(offsets, settings))
        logger.info(f"Buttons ready (gpiod): {self._describe()}")

        while True:
            if not request.wait_edge_events(timedelta(seconds=1)):
                continue
            for event in request.read_edge_events():
                name = offsets.get(event.line_offset)
                if name:
                    self._pressed(name)
            # drop presses that queued up while the display was refreshing
            while request.wait_edge_events(timedelta(0)):
                request.read_edge_events()

    def _run_gpiozero(self):
        from gpiozero import Button

        self._gz_buttons = []
        for name, pin in self.pins.items():
            b = Button(pin, pull_up=True, bounce_time=0.05)
            b.when_pressed = (lambda n=name: threading.Thread(target=self._pressed, args=(n,), daemon=True).start())
            self._gz_buttons.append(b)
        logger.info(f"Buttons ready (gpiozero): {self._describe()}")
        threading.Event().wait()  # keep the thread (and buttons) alive

    def _describe(self):
        return ", ".join(f"{n}=GPIO{p}:{self.actions[n]}" for n, p in sorted(self.pins.items()))

    # -- actions ---------------------------------------------------------------
    def _pressed(self, name):
        now = time.monotonic()
        if now - self.last_press < DEBOUNCE_S:
            return
        self.last_press = now
        if not self.busy.acquire(blocking=False):
            logger.info(f"Button {name} ignored: display is still updating.")
            return
        try:
            action = self.actions.get(name, "none")
            logger.info(f"Button {name} pressed -> {action}")
            self._do(action)
        except Exception:
            logger.exception(f"Button {name} action failed")
        finally:
            self.busy.release()

    def _do(self, action):
        playlist_manager = self.device_config.get_playlist_manager()
        now = self.refresh_task._get_current_datetime()

        with self.refresh_task.condition:
            playlist = playlist_manager.determine_active_playlist(now)
            if not playlist or not playlist.plugins:
                logger.info("No active playlist with plugins; nothing to show.")
                return
            playlist_manager.active_playlist = playlist.name
            count = len(playlist.plugins)
            index = playlist.current_plugin_index

            if action == "next":
                index = 0 if index is None else (index + 1) % count
            elif action == "previous":
                index = 0 if index is None else (index - 1) % count
            elif action == "first":
                index = 0
            elif action == "refresh":
                index = 0 if index is None else index % count
            playlist.current_plugin_index = index
            plugin_instance = playlist.plugins[index]

        logger.info(f"Showing '{plugin_instance.name}' ({index + 1}/{count}) from playlist '{playlist.name}'")
        # next/previous/first reuse a plugin's saved image when it is still
        # fresh (fast on a Pi Zero); refresh always regenerates, as does a
        # plugin that has never been drawn.
        saved = os.path.join(self.device_config.plugin_image_dir, plugin_instance.get_image_path())
        force = action == "refresh" or not os.path.exists(saved)
        self.refresh_task.manual_update(PlaylistRefresh(playlist, plugin_instance, force=force))


def start_buttons(device_config, refresh_task):
    """Start the button handler if enabled. Never raises."""
    try:
        # InkyPi's get_config returns {} (not None) for missing keys.
        enabled = device_config.get_config("buttons_enabled", default=None)
        if enabled is None or enabled == {}:
            enabled = device_config.get_config("display_type", default="inky") == "inky"
        elif isinstance(enabled, str):
            enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
        if not enabled:
            logger.info("Buttons disabled.")
            return None
        handler = ButtonHandler(device_config, refresh_task)
        handler.start()
        return handler
    except Exception:
        logger.exception("Could not start button handler")
        return None
