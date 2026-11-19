from flask import Blueprint, request, jsonify, current_app, render_template
from utils.time_utils import calculate_seconds
import json
from datetime import datetime, timedelta
import os
import logging
from utils.i18n import _
from utils.app_utils import resolve_path, handle_request_files, parse_form


logger = logging.getLogger(__name__)
playlist_bp = Blueprint("playlist", __name__)

@playlist_bp.route('/add_plugin', methods=['POST'])
def add_plugin():
    device_config = current_app.config['DEVICE_CONFIG']
    refresh_task = current_app.config['REFRESH_TASK']
    playlist_manager = device_config.get_playlist_manager()

    try:
        plugin_settings = parse_form(request.form)
        refresh_settings = json.loads(plugin_settings.pop("refresh_settings"))
        plugin_id = plugin_settings.pop("plugin_id")

        playlist = refresh_settings.get('playlist')
        instance_name = refresh_settings.get('instance_name')
        if not playlist:
            return jsonify({"error": _("Playlist name is required")}), 400
        if not instance_name or not instance_name.strip():
            return jsonify({"error": _("Instance name is required")}), 400
        if not all(char.isalpha() or char.isspace() or char.isnumeric() for char in instance_name):
            return jsonify({"error": _("Instance name can only contain alphanumeric characters and spaces")}), 400
        refresh_type = refresh_settings.get('refreshType')
        if not refresh_type or refresh_type not in ["interval", "scheduled"]:
            return jsonify({"error": _("Refresh type is required")}), 400

        existing = playlist_manager.find_plugin(plugin_id, instance_name)
        if existing:
            return jsonify({"error": _("Plugin instance '{name}' already exists", name=instance_name)}), 400

        if refresh_type == "interval":
            unit, interval = refresh_settings.get('unit'), refresh_settings.get("interval")
            if not unit or unit not in ["minute", "hour", "day"]:
                return jsonify({"error": _("Refresh interval unit is required")}), 400
            if not interval:
                return jsonify({"error": _("Refresh interval is required")}), 400
            refresh_interval_seconds = calculate_seconds(int(interval), unit)
            refresh_config = {"interval": refresh_interval_seconds}
        else:
            refresh_time = refresh_settings.get('refreshTime')
            if not refresh_settings.get('refreshTime'):
                return jsonify({"error": _("Refresh time is required")}), 400
            refresh_config = {"scheduled": refresh_time}

        plugin_settings.update(handle_request_files(request.files))
        plugin_dict = {
            "plugin_id": plugin_id,
            "refresh": refresh_config,
            "plugin_settings": plugin_settings,
            "name": instance_name
        }
        result = playlist_manager.add_plugin_to_playlist(playlist, plugin_dict)
        if not result:
            return jsonify({"error": _("Failed to add to playlist")}), 500

        device_config.write_config()
    except Exception as e:
        return jsonify({"error": _("An error occurred: {message}", message=str(e))}), 500
    return jsonify({"success": True, "message": _("Scheduled refresh configured.")})

@playlist_bp.route('/playlist')
def playlists():
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = device_config.get_playlist_manager()
    refresh_info = device_config.get_refresh_info()
    plugins_list = device_config.get_plugins()

    return render_template(
        'playlist.html',
        playlist_config=playlist_manager.to_dict(),
        refresh_info=refresh_info.to_dict(),
        plugins={p["id"]: p for p in plugins_list}
    )

@playlist_bp.route('/create_playlist', methods=['POST'])
def create_playlist():
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = device_config.get_playlist_manager()

    data = request.json
    playlist_name = data.get("playlist_name")
    start_time = data.get("start_time")
    end_time = data.get("end_time")

    if not playlist_name or not playlist_name.strip():
        return jsonify({"error": _("Playlist name is required")}), 400
    if not start_time or not end_time:
        return jsonify({"error": _("Start time and End time are required")}), 400
    if start_time == end_time:
        return jsonify({"error": _("Start and end time must be different")}), 400

    try:
        playlist = playlist_manager.get_playlist(playlist_name)
        if playlist:
            return jsonify({"error": _("Playlist with name '{name}' already exists", name=playlist_name)}), 400

        result = playlist_manager.add_playlist(playlist_name, start_time, end_time)
        if not result:
            return jsonify({"error": _("Failed to create playlist")}), 500

        # save changes to device config file
        device_config.write_config()

    except Exception as e:
        logger.exception("EXCEPTION CAUGHT: " + str(e))
        return jsonify({"error": _("An error occurred: {message}", message=str(e))}), 500

    return jsonify({"success": True, "message": _("Created new Playlist!")})


@playlist_bp.route('/update_playlist/<string:playlist_name>', methods=['PUT'])
def update_playlist(playlist_name):
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = device_config.get_playlist_manager()

    data = request.get_json()

    new_name = data.get("new_name")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    new_name = (new_name or "").strip()
    if not new_name or not start_time or not end_time:
        return jsonify({"success": False, "error": _("Missing required fields")}), 400
    if start_time == end_time:
        return jsonify({"error": _("Start and end time must be different")}), 400

    playlist = playlist_manager.get_playlist(playlist_name)
    if not playlist:
        return jsonify({"error": _("Playlist '{name}' does not exist", name=playlist_name)}), 400

    result = playlist_manager.update_playlist(playlist_name, new_name, start_time, end_time)
    if not result:
        return jsonify({"error": _("Failed to delete playlist")}), 500
    device_config.write_config()

    return jsonify({"success": True, "message": _("Updated playlist '{name}'.", name=playlist_name)})

@playlist_bp.route('/delete_playlist/<string:playlist_name>', methods=['DELETE'])
def delete_playlist(playlist_name):
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = device_config.get_playlist_manager()

    if not playlist_name:
        return jsonify({"error": _("Playlist name is required")}), 400

    playlist = playlist_manager.get_playlist(playlist_name)
    if not playlist:
        return jsonify({"error": _("Playlist '{name}' does not exist", name=playlist_name)}), 400

    # Delete all images associated with plugin instances in this playlist
    from blueprints.plugin import _delete_plugin_instance_images
    for plugin_instance in playlist.plugins:
        _delete_plugin_instance_images(device_config, plugin_instance)

    playlist_manager.delete_playlist(playlist_name)
    device_config.write_config()

    return jsonify({"success": True, "message": _("Deleted playlist '{name}'.", name=playlist_name)})

def _strip_hour_zero(text, time_format):
    """'04:30 PM' -> '4:30 PM' for 12h; 24h times keep their leading zero ('07:30')."""
    return text.lstrip("0") if "%I" in time_format else text


@playlist_bp.app_template_filter('format_relative_time')
def format_relative_time(iso_date_string):
    # Parse the input ISO date string
    dt = datetime.fromisoformat(iso_date_string)

    # Get the timezone from the parsed datetime
    if dt.tzinfo is None:
        raise ValueError("Input datetime doesn't have a timezone.")

    # Get the current time in the same timezone as the input datetime
    now = datetime.now(dt.tzinfo)
    delta = now - dt

    # Compute time difference
    diff_seconds = delta.total_seconds()
    diff_minutes = diff_seconds / 60

    # Define formatting (follow the device's 12h/24h preference)
    time_format = "%I:%M %p"  # Example: 04:30 PM
    try:
        if current_app.config['DEVICE_CONFIG'].get_config("time_format", default="12h") == "24h":
            time_format = "%H:%M"  # Example: 16:30
    except (RuntimeError, KeyError):
        pass  # outside an app context
    month_day_format = "%b %d at " + time_format  # Example: Feb 12 at 04:30 PM

    # Determine relative time string
    if diff_seconds < 120:
        return _("just now")
    elif diff_minutes < 60:
        return _("{n} minutes ago", n=int(diff_minutes))
    elif dt.date() == now.date():
        return _("today at {time}", time=_strip_hour_zero(dt.strftime(time_format), time_format))
    elif dt.date() == (now.date() - timedelta(days=1)):
        return _("yesterday at {time}", time=_strip_hour_zero(dt.strftime(time_format), time_format))
    else:
        # e.g. "Feb 12 at 4:30 PM"; month names come from the catalog (no system locale needed)
        date_label = _("{month} {day}", month=_(dt.strftime("%b")), day=dt.day)
        return _("{date} at {time}", date=date_label, time=_strip_hour_zero(dt.strftime(time_format), time_format))


@playlist_bp.app_template_filter('format_refresh_schedule')
def format_refresh_schedule(refresh):
    """Human readable refresh settings of a plugin instance: 'Every 10 min', 'Daily at 07:30'."""
    refresh = refresh or {}
    if refresh.get("scheduled"):
        return _("Daily at {time}", time=refresh['scheduled'])
    try:
        seconds = int(refresh.get("interval") or 0)
    except (TypeError, ValueError):
        seconds = 0
    if seconds <= 0:
        return ""
    if seconds % 86400 == 0:
        days = seconds // 86400
        return _("Every day") if days == 1 else _("Every {n} days", n=days)
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return _("Every hour") if hours == 1 else _("Every {n} h", n=hours)
    minutes = max(1, round(seconds / 60))
    return _("Every {n} min", n=minutes)


def _find_instance(data):
    """Returns (playlist, plugin_instance, error_response) for a JSON request body."""
    device_config = current_app.config['DEVICE_CONFIG']
    playlist = device_config.get_playlist_manager().get_playlist(data.get("playlist_name"))
    if not playlist:
        return None, None, (jsonify({"error": _("Playlist not found")}), 400)
    plugin_instance = playlist.find_plugin(data.get("plugin_id"), data.get("plugin_instance"))
    if not plugin_instance:
        return playlist, None, (jsonify({"error": _("Plugin instance not found")}), 400)
    return playlist, plugin_instance, None


@playlist_bp.route('/move_plugin_instance', methods=['POST'])
def move_plugin_instance():
    """Moves a plugin instance up or down in its playlist (display order)."""
    data = request.get_json(silent=True) or {}
    direction = data.get("direction")
    if direction not in ("up", "down"):
        return jsonify({"error": _("direction must be 'up' or 'down'")}), 400

    playlist, plugin_instance, error = _find_instance(data)
    if error:
        return error
    playlist.move_plugin(plugin_instance.plugin_id, plugin_instance.name, -1 if direction == "up" else 1)
    current_app.config['DEVICE_CONFIG'].write_config()
    return jsonify({"success": True, "message": (_("Moved '{name}' up.", name=plugin_instance.name) if direction == "up" else _("Moved '{name}' down.", name=plugin_instance.name))})


@playlist_bp.route('/set_plugin_instance_enabled', methods=['POST'])
def set_plugin_instance_enabled():
    """Enables or disables a plugin instance: disabled ones keep their settings but are skipped."""
    data = request.get_json(silent=True) or {}
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        return jsonify({"error": _("enabled must be true or false")}), 400

    playlist, plugin_instance, error = _find_instance(data)
    if error:
        return error
    plugin_instance.enabled = enabled
    current_app.config['DEVICE_CONFIG'].write_config()
    return jsonify({"success": True, "message": (_("'{name}' is back in the rotation.", name=plugin_instance.name) if enabled else _("'{name}' is paused.", name=plugin_instance.name))})


@playlist_bp.route('/display_next', methods=['POST'])
def display_next():
    """Skips to the next plugin of the active playlist and shows it now."""
    refresh_task = current_app.config['REFRESH_TASK']
    if not refresh_task.running:
        return jsonify({"error": _("The refresh task is not running")}), 503
    try:
        refresh_task.display_next()
    except TimeoutError as e:
        return jsonify({"error": str(e)}), 504
    except Exception as e:
        logger.exception("Error while skipping to the next plugin")
        return jsonify({"error": str(e)}), 400
    info = current_app.config['DEVICE_CONFIG'].get_refresh_info()
    return jsonify({"success": True, "message": _("Now showing '{name}'.", name=info.plugin_instance or info.plugin_id),
                    "plugin_instance": info.plugin_instance, "playlist": info.playlist})
