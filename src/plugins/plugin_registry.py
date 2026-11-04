# app_registry.py

import os
import importlib
import logging
from utils.app_utils import resolve_path
from pathlib import Path

logger = logging.getLogger(__name__)
PLUGINS_DIR = 'plugins'
PLUGIN_CLASSES = {}

def load_plugins(plugins_config):
    plugins_module_path = Path(resolve_path(PLUGINS_DIR))
    for plugin in plugins_config:
        plugin_id = plugin.get('id')
        if plugin.get("disabled", False):
            logger.info(f"Plugin {plugin_id} is disabled, skipping.")
            continue

        plugin_dir = plugins_module_path / plugin_id
        if not plugin_dir.is_dir():
            logger.error(f"Could not find plugin directory {plugin_dir} for '{plugin_id}', skipping.")
            continue

        module_path = plugin_dir / f"{plugin_id}.py"
        if not module_path.is_file():
            logger.error(f"Could not find module path {module_path} for '{plugin_id}', skipping.")
            continue

        module_name = f"plugins.{plugin_id}.{plugin_id}"
        try:
            module = importlib.import_module(module_name)
            plugin_class = getattr(module, plugin.get("class"), None)

            if plugin_class:
                # Create an instance of the plugin class and add it to the plugin_classes dictionary
                PLUGIN_CLASSES[plugin_id] = plugin_class(plugin)

        except ImportError as e:
            logging.error(f"Failed to import plugin module {module_name}: {e}")

def get_plugin_instance(plugin_config):
    plugin_id = plugin_config.get("id")
    # Retrieve the plugin class factory function
    plugin_class = PLUGIN_CLASSES.get(plugin_id)
    
    if plugin_class:
        # Initialize the plugin with its configuration
        return plugin_class
    else:
        raise ValueError(f"Plugin '{plugin_id}' is not registered.")

def register_plugin_blueprints(app):
    """Register blueprints from plugins that expose them via get_blueprint() method.
    
    This is a generic mechanism that allows any plugin to register Flask blueprints
    by implementing a get_blueprint() class method that returns a Blueprint instance.
    
    Args:
        app: Flask application instance to register blueprints with
    """
    for plugin_id, plugin_instance in PLUGIN_CLASSES.items():
        try:
            if hasattr(plugin_instance, 'get_blueprint'):
                bp = plugin_instance.get_blueprint()
                if bp:
                    app.register_blueprint(bp)
                    logger.info(f"Registered blueprint for plugin '{plugin_id}'")
        except Exception as e:
            logger.warning(f"Failed to register blueprint for plugin '{plugin_id}': {e}")
