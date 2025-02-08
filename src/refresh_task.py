import threading
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class RefreshTask:
    def __init__(self, device_config, display_manager, playlist_manager):
        self.device_config = device_config
        self.display_manager = display_manager
        self.playlist_manager = playlist_manager

        self.thread = None
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.time_until_refresh = 0
        self.running = False
        self.manual_update_settings = {}

        self.refresh_event = threading.Event()
        self.refresh_event.set()
        self.refresh_result = {}

    def start(self):
        if not self.thread or not self.thread.is_alive():
            logger.info("Starting refresh task")
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.running = True
            self.thread.start()

    def stop(self):
        with self.condition:
            self.running = False
            self.condition.notify_all()  # Wake the thread to let it exit
        if self.thread:
            logger.info("Stopping refresh task")
            self.thread.join()

    def _run(self):
        while True:
            try:
                with self.condition:
                    sleep_time = self.device_config.get_config("scheduler_sleep_time")

                    # Wait for sleep_time or until notified
                    self.condition.wait(timeout=sleep_time)
                    self.refresh_result = {}
                    self.refresh_event.clear()

                    refresh_settings = self.device_config.get_config("refresh_settings")

                    # Exit if `stop()` is called
                    if not self.running:
                        break 

                    # Handle immediate updates
                    if self.manual_update_settings:
                        logger.info("Manual update requested")
                        update_settings = self.manual_update_settings
                        update_display = True
                        self.manual_update_settings = {}
                    else:
                        logger.info(f"Running interval refresh check.")

                        current_datetime = datetime.utcnow()
                        plugin = self.playlist_manager.determine_next_plugin(current_datetime)
                        self.device_config.update_value("playlist_config", self.playlist_manager.to_dict())
                        

                        # Decrement the timer and check if it's time to update
                        self.time_until_refresh -= sleep_time
                        update_display = self.time_until_refresh <= 0
                        update_settings = refresh_settings.get("plugin_settings", {})

                    if self.time_until_refresh <= 0:
                        self.time_until_refresh = refresh_settings.get("interval", 300)

                    if update_display and update_settings:
                        logger.info("Refreshing display...")
                        self.display_manager.display_plugin(update_settings)
                    else:
                        logger.info(f"Next refresh in {self.time_until_refresh} seconds.")

            except Exception as e:
                logger.error(f"Exception during refresh: {e}")
                self.refresh_result["exception"] = e  # Capture exception
            finally:
                self.refresh_event.set()

    def manual_update(self, settings):
        if self.running:
            with self.condition:
                self.manual_update_settings = settings
                self.refresh_result = {}
                self.refresh_event.clear()

                self.condition.notify_all()  # Wake the thread to process manual update

            self.refresh_event.wait(timeout=60)
            if self.refresh_result.get("exception"):
                raise self.refresh_result.get("exception")
        else:
            logger.warn("Background refresh task is not running, unable to do a manual update")

    def update_refresh_settings(self):
        if self.running:
            with self.condition:
                self.time_until_refresh = 0

                self.refresh_result = {}
                self.refresh_event.clear()
                
                self.condition.notify_all()  # Wake the thread to re-evaluate the interval
            
            self.refresh_event.wait(timeout=60)
            if self.refresh_result.get("exception"):
                raise self.refresh_result.get("exception")
        else:
            logger.warn("Background refresh task is not running, unable to update refresh settings")

    


