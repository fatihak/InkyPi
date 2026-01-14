"""
Development Dashboard Blueprint

Provides enhanced development interface with side-by-side preview,
plugin selection, and development tools.
"""

from flask import Blueprint, current_app, render_template, jsonify, request
from plugins.plugin_registry import get_plugin_instance
import logging

logger = logging.getLogger(__name__)
dev_dashboard_bp = Blueprint("dev_dashboard", __name__)


@dev_dashboard_bp.route('/dev/dashboard')
def development_dashboard():
    """Main development dashboard."""
    if not current_app.config.get('SERVE_HTML_MODE', False):
        return jsonify({"error": "HTML serving mode not enabled"}), 404
    
    device_config = current_app.config["DEVICE_CONFIG"]
    
    # Get all available plugins
    plugins = []
    for plugin_config in device_config.get_plugins():
        plugins.append({
            'id': plugin_config.get('id'),
            'name': plugin_config.get('name', plugin_config.get('id')),
            'description': plugin_config.get('description', '')
        })
    
    return render_template('dev_dashboard.html', 
                        plugins=plugins,
                        device_width=device_config.get_resolution()[0],
                        device_height=device_config.get_resolution()[1])


@dev_dashboard_bp.route('/dev/enhanced-preview/<plugin_id>')
def enhanced_plugin_preview(plugin_id):
    """Enhanced preview with side-by-side HTML and screenshot comparison."""
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
        
        # Get plugin instance settings if available
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
            # Get device dimensions
            try:
                device_dimensions = device_config.get_resolution()
                width, height = device_dimensions
            except (KeyError, TypeError, ValueError):
                width, height = 800, 480
            
            # Also generate screenshot for comparison (in production mode)
            screenshot_url = f"/dev/screenshot/{plugin_id}"
            
            return render_template('enhanced_preview.html',
                             plugin_id=plugin_id,
                             plugin_name=plugin_config.get('name', plugin_id),
                             rendered_html=result['html'],
                             css_files=result['css_files'],
                             template_params=result['template_params'],
                             device_width=width,
                             device_height=height,
                             screenshot_url=screenshot_url)
        else:
            return jsonify({"error": "Plugin did not return HTML content"}), 500
            
    except Exception as e:
        logger.exception(f"Error generating enhanced preview for {plugin_id}: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@dev_dashboard_bp.route('/dev/screenshot/<plugin_id>')
def plugin_screenshot(plugin_id):
    """Generate screenshot of plugin for comparison."""
    if not current_app.config.get('SERVE_HTML_MODE', False):
        return jsonify({"error": "HTML serving mode not enabled"}), 404
    
    device_config = current_app.config["DEVICE_CONFIG"]
    
    # Find the plugin by id
    plugin_config = device_config.get_plugin(plugin_id)
    if not plugin_config:
        return jsonify({"error": f"Plugin '{plugin_id}' not found"}), 404
    
    try:
        # Temporarily disable HTML serving mode to get screenshot
        original_serve_html = current_app.config.get('SERVE_HTML_MODE', False)
        current_app.config['SERVE_HTML_MODE'] = False
        
        # Get plugin instance and generate screenshot
        plugin = get_plugin_instance(plugin_config)
        
        # Get plugin instance settings if available
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
        
        # Generate screenshot (will take screenshot in production mode)
        result = plugin.generate_image(settings, device_config)
        
        # Restore HTML serving mode
        current_app.config['SERVE_HTML_MODE'] = original_serve_html
        
        if hasattr(result, 'save'):
            # Convert PIL image to base64 for display
            import io
            import base64
            
            buffer = io.BytesIO()
            result.save(buffer, format='PNG')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            return jsonify({
                'screenshot': f"data:image/png;base64,{image_base64}",
                'width': result.width,
                'height': result.height
            })
        else:
            return jsonify({"error": "Unable to generate screenshot"}), 500
            
    except Exception as e:
        # Restore HTML serving mode in case of error
        current_app.config['SERVE_HTML_MODE'] = original_serve_html
        logger.exception(f"Error generating screenshot for {plugin_id}: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@dev_dashboard_bp.route('/dev/plugin-info/<plugin_id>')
def plugin_info(plugin_id):
    """Get detailed information about a plugin."""
    if not current_app.config.get('SERVE_HTML_MODE', False):
        return jsonify({"error": "HTML serving mode not enabled"}), 404
    
    device_config = current_app.config["DEVICE_CONFIG"]
    
    # Find the plugin by id
    plugin_config = device_config.get_plugin(plugin_id)
    if not plugin_config:
        return jsonify({"error": f"Plugin '{plugin_id}' not found"}), 404
    
    try:
        # Get plugin instance to extract more information
        plugin = get_plugin_instance(plugin_config)
        
        plugin_info = {
            'id': plugin_config.get('id'),
            'name': plugin_config.get('name', plugin_config.get('id')),
            'description': plugin_config.get('description', ''),
            'config': plugin_config,
            'has_render_method': hasattr(plugin, 'generate_settings_template'),
            'supports_live_reload': True  # All plugins using render_image support it
        }
        
        return jsonify(plugin_info)
        
    except Exception as e:
        logger.exception(f"Error getting plugin info for {plugin_id}: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500