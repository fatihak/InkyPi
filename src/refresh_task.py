import threading
import time
import os
import logging
from datetime import datetime
from plugins.plugin_registry import get_plugin_instance
from PIL import Image

logger = logging.getLogger(__name__)

class RefreshTask:
    def __init__(self, device_config, display_manager, playlist_manager):
        self.device_config = device_config
        self.display_manager = display_manager
        self.playlist_manager = playlist_manager

        self.thread = None
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
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

                    image = None
                    # Handle immediate updates
                    if self.manual_update_settings:
                        logger.info("Manual update requested")
                        update_settings = self.manual_update_settings
                        self.manual_update_settings = {}
                    else:
                        logger.info(f"Running interval refresh check.")

                        current_datetime = datetime.utcnow()
                        plugin = self.playlist_manager.determine_next_plugin(current_datetime)

                        if not plugin:
                            logger.info("No plugin to display.")
                            continue
                        
                        # determine if the image should be refreshed
                        should_refresh = plugin.should_refresh(current_datetime)
                        
                        plugin_image_dir = os.path.join(self.device_config.plugin_image_dir, plugin.get_image_path())
                        if should_refresh:
                            logger.info("Refreshing plugin")
                            image = self.refresh_plugin(plugin.plugin_id, plugin.settings)

                            image.save(plugin_image_dir)
                            plugin.latest_refresh = current_datetime.isoformat()
                        else:
                            logger.info("Using latest image")
                            image = Image.open(plugin_image_dir)
                        self.playlist_manager.latest_refresh = current_datetime.isoformat()
                        self.device_config.update_value("playlist_config", self.playlist_manager.to_dict())                            

                    if False and image:
                        logger.info("Refreshing display...")
                        self.display_manager.display_image(image)

            except Exception as e:
                logging.exception('Exception during refresh')
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
    
    def refresh_plugin(self, plugin_id, plugin_settings):
        plugin_config = next((plugin for plugin in self.device_config.get_plugins() if plugin['id'] == plugin_id), None)

        if not plugin_config:
            raise ValueError(f"Plugin '{plugin_id}' not found.")

        plugin_instance = get_plugin_instance(plugin_config)
        image = plugin_instance.generate_image(plugin_settings, self.device_config)

        return image


    


