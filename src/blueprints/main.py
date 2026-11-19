from flask import Blueprint, request, jsonify, current_app, render_template, send_file
import os
from datetime import datetime, timedelta
from utils.i18n import _

main_bp = Blueprint("main", __name__)

def display_status(device_config):
    """What is on the display now, for the home page header."""
    info = device_config.get_refresh_info().to_dict()
    plugins = {p["id"]: _(p.get("display_name", p["id"])) for p in device_config.get_plugins()}
    plugin_name = plugins.get(info.get("plugin_id"), info.get("plugin_id") or "")
    status = {
        "has_image": bool(info.get("refresh_time")),
        "title": info.get("plugin_instance") or plugin_name or _("Nothing displayed yet"),
        "plugin": plugin_name,
        "playlist": info.get("playlist") or "",
        "manual": info.get("refresh_type") == "Manual Update",
        "refreshed": "",
        "next_change": "",
    }
    refresh_time = info.get("refresh_time")
    if refresh_time:
        try:
            from blueprints.playlist import format_relative_time
            refreshed_dt = datetime.fromisoformat(refresh_time)
            status["refreshed"] = format_relative_time(refresh_time)
            interval = int(device_config.get_config("plugin_cycle_interval_seconds", default=3600) or 3600)
            next_dt = refreshed_dt + timedelta(seconds=interval)
            fmt = "%H:%M" if device_config.get_config("time_format", default="12h") == "24h" else "%I:%M %p"
            if next_dt > datetime.now(refreshed_dt.tzinfo):
                status["next_change"] = next_dt.strftime(fmt).lstrip("0") if "%p" in fmt else next_dt.strftime(fmt)
        except (ValueError, TypeError):
            pass
    return status


@main_bp.route('/')
def main_page():
    device_config = current_app.config['DEVICE_CONFIG']
    return render_template('inky.html', config=device_config.get_config(), plugins=device_config.get_plugins(),
                           status=display_status(device_config))


@main_bp.route('/api/status')
def get_status():
    return jsonify(display_status(current_app.config['DEVICE_CONFIG']))

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