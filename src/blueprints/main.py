from flask import Blueprint, request, jsonify, current_app, render_template, send_file
import logging
import os
from datetime import datetime
from refresh_task import PlaylistRefresh

logger = logging.getLogger(__name__)
main_bp = Blueprint("main", __name__)

@main_bp.route('/')
def main_page():
    device_config = current_app.config['DEVICE_CONFIG']
    return render_template('inky.html', config=device_config.get_config(), plugins=device_config.get_plugins())

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


@main_bp.route('/api/refresh', methods=['POST'])
def refresh_current():
    """Regenerate what the display is currently showing, ignoring the refresh interval.

    Meant for external triggers (e.g. a Home Assistant automation or a webhook) that want the
    display updated now instead of waiting for the next scheduled refresh. The item to refresh is
    taken from the latest refresh info, so callers do not need to know playlist or plugin names.
    """
    device_config = current_app.config['DEVICE_CONFIG']
    refresh_task = current_app.config['REFRESH_TASK']

    def error(message, status):
        return jsonify({"success": False, "error": message}), status

    if not refresh_task.running:
        return error("The refresh task is not running.", 503)

    info = device_config.get_refresh_info()
    if not info.plugin_id:
        return error("Nothing has been displayed yet, there is nothing to refresh.", 409)
    if info.refresh_type != "Playlist":
        # A manual "Update now" is not stored in a playlist, so its settings cannot be replayed.
        return error("The current image comes from a manual update and is not part of a playlist, "
                     "so it cannot be refreshed. Add it to a playlist to enable this.", 409)

    playlist = device_config.get_playlist_manager().get_playlist(info.playlist)
    plugin_instance = playlist.find_plugin(info.plugin_id, info.plugin_instance) if playlist else None
    if not plugin_instance:
        return error(f"The plugin instance '{info.plugin_instance}' shown on the display no longer "
                     f"exists in playlist '{info.playlist}'.", 409)

    try:
        refresh_task.manual_update(PlaylistRefresh(playlist, plugin_instance, force=True))
    except Exception as e:
        logger.exception("Error in refresh_current")
        return error(f"An error occurred: {str(e)}", 500)

    return jsonify({
        "success": True,
        "message": "Display refreshed",
        "playlist": playlist.name,
        "plugin_id": plugin_instance.plugin_id,
        "plugin_instance": plugin_instance.name,
    }), 200
