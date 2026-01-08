#!/usr/bin/env python3

# set up logging
import os, logging.config

from pi_heif import register_heif_opener

logging.config.fileConfig(
    os.path.join(os.path.dirname(__file__), "config", "logging.conf")
)

# suppress warning from inky library https://github.com/pimoroni/inky/issues/205
import warnings

warnings.filterwarnings("ignore", message=".*Busy Wait: Held high.*")

import os
import random
import time
import sys
import json
import logging
import threading
import argparse
from utils.app_utils import generate_startup_image
from flask import Flask, request
from werkzeug.serving import is_running_from_reloader
from config import Config
from display.display_manager import DisplayManager
from refresh_task import RefreshTask
from blueprints.main import main_bp
from blueprints.settings import settings_bp
from blueprints.plugin import plugin_bp
from blueprints.playlist import playlist_bp
from blueprints.dev import dev_bp
from jinja2 import ChoiceLoader, FileSystemLoader
from plugins.plugin_registry import load_plugins
from waitress import serve

# Development-only imports (only available when requirements-dev.txt is used)
try:
    from flask_socketio import SocketIO
    from utils.file_watcher import LiveReloadManager
    from blueprints.dev import register_socketio_events
    DEV_DEPS_AVAILABLE = True
except ImportError:
    DEV_DEPS_AVAILABLE = False
    SocketIO = None
    LiveReloadManager = None
    register_socketio_events = None


logger = logging.getLogger(__name__)

# Parse command line arguments
parser = argparse.ArgumentParser(description="InkyPi Display Server")
parser.add_argument("--dev", action="store_true", help="Run in development mode")
parser.add_argument("--serve-html", action="store_true", help="Serve HTML instead of rendering images (requires --dev)")
args = parser.parse_args()

# Set development mode settings
if args.dev:
    Config.config_file = os.path.join(Config.BASE_DIR, "config", "device_dev.json")
    DEV_MODE = True
    PORT = 8080
    
    if args.serve_html:
        SERVE_HTML_MODE = True
        logger.info("Starting InkyPi in DEVELOPMENT mode with HTML serving on port 8080")
    else:
        SERVE_HTML_MODE = False
        logger.info("Starting InkyPi in DEVELOPMENT mode on port 8080")
else:
    DEV_MODE = False
    SERVE_HTML_MODE = False
    PORT = 80
    if args.serve_html:
        logger.error("--serve-html requires --dev mode")
        sys.exit(1)
    logger.info("Starting InkyPi in PRODUCTION mode on port 80")
logging.getLogger("waitress.queue").setLevel(logging.ERROR)
app = Flask(__name__)

# Initialize SocketIO for live reload (development dependencies required)
if SERVE_HTML_MODE and DEV_DEPS_AVAILABLE:
    socketio = SocketIO(app, cors_allowed_origins="*")
    live_reload_manager = None
elif SERVE_HTML_MODE and not DEV_DEPS_AVAILABLE:
    logger.error("HTML serving mode requires development dependencies. Please install with: pip install -r install/requirements-dev.txt")
    sys.exit(1)
else:
    socketio = None
    live_reload_manager = None

template_dirs = [
    os.path.join(os.path.dirname(__file__), "templates"),  # Default template folder
    os.path.join(os.path.dirname(__file__), "plugins"),  # Plugin templates
]
app.jinja_loader = ChoiceLoader(
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
app.config["DEV_MODE"] = DEV_MODE
app.config["SERVE_HTML_MODE"] = SERVE_HTML_MODE

# Set additional parameters
app.config["MAX_FORM_PARTS"] = 10_000

# Register Blueprints
app.register_blueprint(main_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(plugin_bp)
app.register_blueprint(playlist_bp)
app.register_blueprint(dev_bp)

# Register SocketIO events if in HTML serving mode and development deps available
if SERVE_HTML_MODE and socketio and register_socketio_events:
    register_socketio_events(socketio)

# Register opener for HEIF/HEIC images
register_heif_opener()

if __name__ == "__main__":
    # start the background refresh task
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

        # Get local IP address for display (only in dev mode when running on non-Pi)
        if DEV_MODE:
            import socket

            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
                logger.info(f"Serving on http://{local_ip}:{PORT}")
            except:
                pass  # Ignore if we can't get the IP

        # Start live reload manager if in HTML serving mode and dependencies available
        if SERVE_HTML_MODE and socketio and LiveReloadManager:
            live_reload_manager = LiveReloadManager(socketio)
            live_reload_manager.start_watching()
            logger.info("Live reload file watching started")
            
            # Run with SocketIO instead of waitress for live reload support
            try:
                socketio.run(app, host="0.0.0.0", port=PORT, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
            finally:
                if live_reload_manager:
                    live_reload_manager.stop_watching()
        else:
            # Use waitress for production or non-HTML serving modes
            serve(app, host="0.0.0.0", port=PORT, threads=1)
    finally:
        refresh_task.stop()
