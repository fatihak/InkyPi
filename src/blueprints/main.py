from flask import Blueprint, request, jsonify, current_app, render_template, send_file, make_response
import os
from datetime import datetime

main_bp = Blueprint("main", __name__)

@main_bp.route('/')
def main_page():
    device_config = current_app.config['DEVICE_CONFIG']
    # Show buttons only if enabled in settings AND visible in UI
    buttons_enabled = device_config.get_config("buttons_enabled", default=True)
    show_buttons = buttons_enabled and device_config.get_config("show_buttons", default=True)
    response = make_response(render_template(
        'inky.html', 
        config=device_config.get_config(), 
        plugins=device_config.get_plugins(),
        show_buttons=show_buttons
    ))
    # Prevent caching so settings changes apply immediately
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

@main_bp.route('/api/current_image')
def get_current_image():
    """Serve current_image.png with conditional request support (If-Modified-Since)."""
    image_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'images', 'current_image.png')
    
    if not os.path.exists(image_path):
        return jsonify({"error": "Image not found"}), 404
    
    # Get the file's last modified time (truncate to seconds to match HTTP header precision)
    file_mtime = int(os.path.getmtime(image_path))
    last_modified = datetime.fromtimestamp(file_mtime)
    
    # Check If-Modified-Since header
    if_modified_since = request.headers.get('If-Modified-Since')
    if if_modified_since:
        try:
            # Parse the If-Modified-Since header
            client_mtime = datetime.strptime(if_modified_since, '%a, %d %b %Y %H:%M:%S %Z')
            client_mtime_seconds = int(client_mtime.timestamp())
            
            # Compare (both now in seconds, no sub-second precision)
            if file_mtime <= client_mtime_seconds:
                return '', 304
        except (ValueError, AttributeError):
            pass
    
    # Send the file with Last-Modified header
    response = send_file(image_path, mimetype='image/png')
    response.headers['Last-Modified'] = last_modified.strftime('%a, %d %b %Y %H:%M:%S GMT')
    response.headers['Cache-Control'] = 'no-cache'
    return response


@main_bp.route('/api/status')
def get_status():
    """Get current system status including refresh state."""
    refresh_task = current_app.config['REFRESH_TASK']
    device_config = current_app.config['DEVICE_CONFIG']
    
    refresh_info = device_config.get_refresh_info()
    refresh_status = refresh_task.get_status()
    
    return jsonify({
        "is_refreshing": refresh_status["is_refreshing"],
        "refresh_duration": refresh_status["refresh_duration"],
        "current_plugin": refresh_info.plugin_id,
        "current_instance": refresh_info.plugin_instance,
        "playlist": refresh_info.playlist
    })


@main_bp.route('/api/plugin_order', methods=['POST'])
def save_plugin_order():
    """Save the custom plugin order."""
    device_config = current_app.config['DEVICE_CONFIG']

    data = request.get_json() or {}
    order = data.get('order', [])

    if not isinstance(order, list):
        return jsonify({"error": "Order must be a list"}), 400

    device_config.set_plugin_order(order)

    return jsonify({"success": True})

