#!/usr/bin/env python3

# set up logging
import logging.config
import os

logging.config.fileConfig(
    os.path.join(os.path.dirname(__file__), "config", "logging.conf")
)

# suppress warning from inky library https://github.com/pimoroni/inky/issues/205
import warnings

warnings.filterwarnings("ignore", message=".*Busy Wait: Held high.*")

import logging
import os
import random

from flask import Flask
from jinja2 import ChoiceLoader, FileSystemLoader

from inkypi.blueprints.main import main_bp
from inkypi.blueprints.playlist import playlist_bp
from inkypi.blueprints.plugin import plugin_bp
from inkypi.blueprints.settings import settings_bp
from inkypi.config import Config
from inkypi.display.display_manager import DisplayManager
from inkypi.plugins.plugin_registry import load_plugins
from inkypi.refresh_task import RefreshTask
from inkypi.utils.app_utils import generate_startup_image

logger = logging.getLogger(__name__)

logger.info("Starting web server")
app = Flask(__name__)
template_dirs = [
    os.path.join(os.path.dirname(__file__), "templates"),  # Default template folder
    os.path.join(os.path.dirname(__file__), "plugins"),  # Plugin templates
]
app.jinja_loader = ChoiceLoader(  # type: ignore
    [FileSystemLoader(directory) for directory in template_dirs]
)

device_config = Config()
display_manager = DisplayManager(device_config)
refresh_task = RefreshTask(device_config, display_manager)

load_plugins(device_config.get_plugins())

# Store dependencies
app.config["DEVICE_CONFIG"] = device_config
app.config["DISPLAY_MANAGER"] = display_manager
app.config["REFRESH_TASK"] = refresh_task

# Set additional parameters
app.config["MAX_FORM_PARTS"] = 10_000

# Register Blueprints
app.register_blueprint(main_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(plugin_bp)
app.register_blueprint(playlist_bp)

if __name__ == "__main__":
    from werkzeug.serving import is_running_from_reloader

    # start the background refresh task
    if not is_running_from_reloader():
        refresh_task.start()

    # display default inkypi image on startup
    if device_config.get_config("startup") is True:
        logger.info("Startup flag is set, displaying startup image")
        img = generate_startup_image(device_config.get_resolution())
        display_manager.display_image(img)
        device_config.update_value("startup", False, write=True)

    try:
        # Run the Flask app
        app.secret_key = str(random.randint(100000, 999999))
        app.run(host="0.0.0.0", port=80)
    finally:
        refresh_task.stop()
