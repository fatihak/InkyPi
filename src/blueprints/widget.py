from flask import Blueprint, request, jsonify, current_app, render_template
from utils.app_utils import parse_form, handle_request_files
from widgets.widget_registry import get_widget_instance
import logging

logger = logging.getLogger(__name__)
widget_bp = Blueprint("widget", __name__)

@widget_bp.route('/widgets')
def widgets_page():
    """Display widget management page."""
    device_config = current_app.config['DEVICE_CONFIG']
    all_widgets = device_config.get_widgets()
    
    enabled_widget_ids = device_config.get_config('widget_settings', {}).get('enabled_widgets', [])
    enabled_widgets = [o for o in all_widgets if o['id'] in enabled_widget_ids]
    # Maintain order from enabled_widgets list
    enabled_widgets.sort(key=lambda x: enabled_widget_ids.index(x['id']))
    available_widgets = [o for o in all_widgets if o['id'] not in enabled_widget_ids]
    
    widget_settings = device_config.get_config('widget_settings', {})
    
    return render_template(
        'widgets.html',
        enabled_widgets=enabled_widgets,
        available_widgets=available_widgets,
        widget_settings=widget_settings
    )

@widget_bp.route('/api/widgets/reorder', methods=['POST'])
def reorder_widgets():
    """Reorder enabled widgets."""
    device_config = current_app.config['DEVICE_CONFIG']
    try:
        data = request.get_json()
        new_order = data.get('order', [])
        
        # Validate that all IDs are valid widgets
        widgets = device_config.get_widgets()
        all_widget_ids = {w['id'] for w in widgets}
        
        if not all(w_id in all_widget_ids for w_id in new_order):
            return jsonify({"error": "Invalid widget IDs"}), 400
        
        widget_settings = device_config.get_config('widget_settings', {})
        widget_settings['enabled_widgets'] = new_order
        device_config.update_value('widget_settings', widget_settings, write=True)
        
        logger.info(f"Widget order updated: {new_order}")
        return jsonify({"success": True, "message": "Widget order updated"}), 200
    except Exception as e:
        logger.exception(f"Error reordering widgets: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@widget_bp.route('/api/widgets/toggle', methods=['POST'])
def toggle_widget():
    """Enable or disable a widget."""
    device_config = current_app.config['DEVICE_CONFIG']
    try:
        data = request.get_json()
        widget_id = data.get('widget_id')
        enable = data.get('enable', True)
        
        # Validate widget exists
        widget_config = device_config.get_widget(widget_id)
        if not widget_config:
            return jsonify({"error": f"Widget '{widget_id}' not found"}), 404
        
        widget_settings = device_config.get_config('widget_settings', {})
        enabled_widgets = widget_settings.get('enabled_widgets', [])
        
        if enable and widget_id not in enabled_widgets:
            enabled_widgets.append(widget_id)
        elif not enable and widget_id in enabled_widgets:
            enabled_widgets.remove(widget_id)
        
        widget_settings['enabled_widgets'] = enabled_widgets
        device_config.update_value('widget_settings', widget_settings, write=True)
        
        logger.info(f"Widget '{widget_id}' {'enabled' if enable else 'disabled'}")
        return jsonify({"success": True, "message": f"Widget {'enabled' if enable else 'disabled'}"}), 200
    except Exception as e:
        logger.exception(f"Error toggling widget: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@widget_bp.route('/api/widgets/settings', methods=['POST'])
def save_widget_settings():
    """Save widget positioning and spacing settings."""
    device_config = current_app.config['DEVICE_CONFIG']
    try:
        data = request.get_json()
        
        widget_settings = device_config.get_config('widget_settings', {})
        widget_settings['corner'] = data.get('corner', widget_settings.get('corner', 'top-left'))
        widget_settings['orientation'] = data.get('orientation', widget_settings.get('orientation', 'horizontal'))
        widget_settings['spacing'] = int(data.get('spacing', widget_settings.get('spacing', 10)))
        widget_settings['margin'] = int(data.get('margin', widget_settings.get('margin', 10)))
        
        device_config.update_value('widget_settings', widget_settings, write=True)
        
        logger.info(f"Widget settings updated: corner={widget_settings['corner']}, orientation={widget_settings['orientation']}, spacing={widget_settings['spacing']}, margin={widget_settings['margin']}")
        return jsonify({"success": True, "message": "Widget settings saved"}), 200
    except Exception as e:
        logger.exception(f"Error saving widget settings: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@widget_bp.route('/api/widgets/<widget_id>/settings', methods=['POST'])
def save_widget_config(widget_id):
    """Save configuration for a specific widget."""
    device_config = current_app.config['DEVICE_CONFIG']
    try:
        # Get widget settings structure
        widget_settings = device_config.get_config('widget_settings', {})
        if 'widgets' not in widget_settings:
            widget_settings['widgets'] = {}
        
        plugin_settings = parse_form(request.form)
        plugin_settings.update(handle_request_files(request.files, request.form))
        
        # Remove plugin_id if it crept in
        plugin_settings.pop('plugin_id', None)
        plugin_settings.pop('widget_id', None)

        # Check contrast color value
        use_contrast_color = (
            plugin_settings.pop('use_contrast_color', 'false') == 'true'
        )
        
        # Save
        widget_settings['widgets'][widget_id] = plugin_settings
        widget_settings['widgets'][widget_id]['use_contrast_color'] = use_contrast_color
        device_config.update_value('widget_settings', widget_settings, write=True)
        
        logger.info(f"Saved settings for widget '{widget_id}'")
        return jsonify({"success": True, "message": "Widget settings saved"}), 200
    except Exception as e:
        logger.exception(f"Error saving widget settings: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@widget_bp.route('/widgets/<widget_id>')
def widget_settings_page(widget_id):
    device_config = current_app.config['DEVICE_CONFIG']
    
    # Find the widget by id
    widget_config = device_config.get_widget(widget_id)
    if widget_config:
        try:
            widget = get_widget_instance(widget_config)
            
            template_params = widget.generate_settings_template()
            template_params.setdefault("plugin_settings", {})

            # Load settings from widget config
            widget_settings = device_config.get_config('widget_settings', {})
            specific_widget_settings = widget_settings.get('widgets', {}).get(widget_id)

            # Update template_params with specific_widget_settings to ensure values like use_contrast_color are correct
            if specific_widget_settings is not None:
                template_params.update(specific_widget_settings)
            else:
                specific_widget_settings = {}
            
            return render_template('widget_settings.html', widget=widget_config, widget_settings=specific_widget_settings, **template_params)
        except Exception as e:
            logger.exception("EXCEPTION CAUGHT: " + str(e))
            return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    else:
        return "Widget not found", 404
