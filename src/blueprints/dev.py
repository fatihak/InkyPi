from flask import Blueprint, current_app, render_template, jsonify
from plugins.plugin_registry import get_plugin_instance
import logging

logger = logging.getLogger(__name__)
dev_bp = Blueprint("dev", __name__)


@dev_bp.route('/dev/preview/<plugin_id>')
def plugin_preview(plugin_id):
    """Serve HTML preview of a plugin."""
    if not current_app.config.get('SERVE_HTML_MODE', False):
        return jsonify({"error": "HTML serving mode not enabled"}), 404
    
    device_config = current_app.config["DEVICE_CONFIG"]
    
    # Find the plugin by id
    plugin_config = device_config.get_plugin(plugin_id)
    if not plugin_config:
        return jsonify({"error": f"Plugin '{plugin_id}' not found"}), 404
    
    try:
        # Get plugin instance and generate HTML
        plugin = get_plugin_instance(plugin_config)
        
        # Use default settings or the first instance's settings
        playlist_manager = device_config.get_playlist_manager()
        plugin_instance = None
        for playlist in playlist_manager.playlists:
            for instance in playlist.plugins:
                if instance.plugin_id == plugin_id:
                    plugin_instance = instance
                    break
            if plugin_instance:
                break
        
        settings = plugin_instance.settings if plugin_instance else {}
        
        # Generate HTML content
        result = plugin.generate_image(settings, device_config)
        
        if isinstance(result, dict) and 'html' in result:
            # Get device dimensions from config, with fallback to defaults
            try:
                device_dimensions = device_config.get_resolution()
                width, height = device_dimensions
            except (KeyError, TypeError, ValueError):
                # Fallback to defaults if config is missing or invalid
                width, height = 800, 480
            
            return render_template('dev_preview.html', 
                                 plugin_id=plugin_id,
                                 plugin_name=plugin_config.get('name', plugin_id),
                                 rendered_html=result['html'],
                                 css_files=result['css_files'],
                                 template_params=result['template_params'],
                                 device_width=width,
                                 device_height=height)
        else:
            return jsonify({"error": "Plugin did not return HTML content"}), 500
            
    except Exception as e:
        logger.exception(f"Error generating preview for {plugin_id}: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@dev_bp.route('/dev/preview/<plugin_id>/<instance_name>')
def plugin_instance_preview(plugin_id, instance_name):
    """Serve HTML preview of a specific plugin instance."""
    if not current_app.config.get('SERVE_HTML_MODE', False):
        return jsonify({"error": "HTML serving mode not enabled"}), 404
    
    device_config = current_app.config["DEVICE_CONFIG"]
    playlist_manager = device_config.get_playlist_manager()
    
    # Find the plugin instance
    plugin_instance = None
    for playlist in playlist_manager.playlists:
        found_instance = playlist.find_plugin(plugin_id, instance_name)
        if found_instance:
            plugin_instance = found_instance
            break
    
    if not plugin_instance:
        return jsonify({"error": f"Plugin instance '{instance_name}' not found"}), 404
    
    try:
        # Get plugin configuration
        plugin_config = device_config.get_plugin(plugin_id)
        if not plugin_config:
            return jsonify({"error": f"Plugin '{plugin_id}' not found"}), 404
        
        # Get plugin instance and generate HTML
        plugin = get_plugin_instance(plugin_config)
        
        # Generate HTML content
        result = plugin.generate_image(plugin_instance.settings, device_config)
        
        if isinstance(result, dict) and 'html' in result:
            # Get device dimensions from config, with fallback to defaults
            try:
                device_dimensions = device_config.get_resolution()
                width, height = device_dimensions
            except (KeyError, TypeError, ValueError):
                # Fallback to defaults if config is missing or invalid
                width, height = 800, 480
            
            return render_template('dev_preview.html', 
                                 plugin_id=plugin_id,
                                 instance_name=instance_name,
                                 plugin_name=f"{plugin_config.get('name', plugin_id)} - {instance_name}",
                                 rendered_html=result['html'],
                                 css_files=result['css_files'],
                                 template_params=result['template_params'],
                                 device_width=width,
                                 device_height=height)
        else:
            return jsonify({"error": "Plugin did not return HTML content"}), 500
            
    except Exception as e:
        logger.exception(f"Error generating preview for {plugin_id}/{instance_name}: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@dev_bp.route('/dev/plugins')
def list_plugins():
    """List available plugins for preview."""
    if not current_app.config.get('SERVE_HTML_MODE', False):
        return jsonify({"error": "HTML serving mode not enabled"}), 404
    
    device_config = current_app.config["DEVICE_CONFIG"]
    plugins = []
    
    for plugin_config in device_config.get_plugins():
        plugins.append({
            'id': plugin_config.get('id'),
            'name': plugin_config.get('name', plugin_config.get('id')),
            'description': plugin_config.get('description', ''),
            'preview_url': f"/dev/preview/{plugin_config.get('id')}"
        })
    
    return jsonify({"plugins": plugins})