import os
import json
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class Config:
    # Base path for the project directory
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # File paths relative to the script's directory
    config_file = os.path.join(BASE_DIR, "config", "device.json")
    plugins_file = os.path.join(BASE_DIR, "plugins", "plugins.json")

    current_image_file = os.path.join(BASE_DIR, "static", "images", "current_image.png")

    def __init__(self):
        logger.info(self.config_file)
        self.config = self.read_config()
        self.plugins_list = self.read_plugins_list()
    
    def read_config(self):
        logger.info(f"Reading device config from {self.config_file}")
        with open(self.config_file) as f:
            config = json.load(f)
        return config
    
    def read_plugins_list(self):
        logger.info(f"Reading plugins list from from {self.plugins_file}")
        with open(self.plugins_file) as f:
            plugins_list = json.load(f)
        return plugins_list

    def write_config(self):
        logger.info(f"Writing device config to {self.config_file}")
        with open(self.config_file, 'w') as outfile:
            json.dump(self.config, outfile, indent=4)

    def get_config(self, key=None):
        if key is not None:
            return self.config.get(key, {})
        return self.config

    def get_plugins(self):
        return self.plugins_list

    def get_resolution(self):
        resolution = self.get_config("resolution")
        width, height = resolution
        return (int(width), int(height))

    def update_config(self, config):
        self.config.update(config)
        self.write_config()

    def update_value(self, key, value):
        self.config[key] = value
        self.write_config()
    
    def load_env_key(self, key):
        load_dotenv(override=True)
        return os.getenv(key)