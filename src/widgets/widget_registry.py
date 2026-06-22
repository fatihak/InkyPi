import importlib
import logging
from utils.app_utils import resolve_path
from pathlib import Path

logger = logging.getLogger(__name__)
WIDGETS_DIR = 'widgets'
WIDGET_CLASSES = {}

def load_widgets(widgets_config):
    widgets_module_path = Path(resolve_path(WIDGETS_DIR))
    for widget in widgets_config:
        widget_id = widget.get('id')
        if widget.get("disabled", False):
            logging.info(f"Widget {widget_id} is disabled, skipping.")
            continue

        widget_dir = widgets_module_path / widget_id
        if not widget_dir.is_dir():
            logging.error(f"Could not find widget directory {widget_dir} for '{widget_id}', skipping.")
            continue

        module_path = widget_dir / f"{widget_id}.py"
        if not module_path.is_file():
            logging.error(f"Could not find module path {module_path} for '{widget_id}', skipping.")
            continue

        module_name = f"widgets.{widget_id}.{widget_id}"
        try:
            module = importlib.import_module(module_name)
            widget_class = getattr(module, widget.get("class"), None)

            if widget_class:
                # Create an instance of the widget class and add it to the widget_classes dictionary
                WIDGET_CLASSES[widget_id] = widget_class(widget)

        except ImportError as e:
            logging.error(f"Failed to import widget module {module_name}: {e}")

def get_widget_instance(widget_config):
    widget_id = widget_config.get("id")
    # Retrieve the widget class factory function
    widget_data = WIDGET_CLASSES.get(widget_id)
    
    if widget_data:
        # Initialize the widget with its configuration
        return widget_data
    else:
        raise ValueError(f"Widget '{widget_id}' is not registered.")
