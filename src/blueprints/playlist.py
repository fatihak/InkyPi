from flask import Blueprint, request, jsonify, current_app, render_template
from utils.time_utils import calculate_seconds
import json
from datetime import datetime, timedelta
import os
import logging
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
            return jsonify({"error": "Playlist name is required"}), 400
        if not instance_name or not instance_name.strip():
            return jsonify({"error": "Instance name is required"}), 400
        if not all(char.isalpha() or char.isspace() or char.isnumeric() for char in instance_name):
            return jsonify({"error": "Instance name can only contain alphanumeric characters and spaces"}), 400
        refresh_type = refresh_settings.get('refreshType')
        if not refresh_type or refresh_type not in ["interval", "scheduled"]:
            return jsonify({"error": "Refresh type is required"}), 400

        existing = playlist_manager.find_plugin(plugin_id, instance_name)
        if existing:
            return jsonify({"error": f"Plugin instance '{instance_name}' already exists"}), 400

        if refresh_type == "interval":
            unit, interval = refresh_settings.get('unit'), refresh_settings.get("interval")
            if not unit or unit not in ["minute", "hour", "day"]:
                return jsonify({"error": "Refresh interval unit is required"}), 400
            if not interval:
                return jsonify({"error": "Refresh interval is required"}), 400
            refresh_interval_seconds = calculate_seconds(int(interval), unit)
            refresh_config = {"interval": refresh_interval_seconds}
        else:
            refresh_time = refresh_settings.get('refreshTime')
            if not refresh_settings.get('refreshTime'):
                return jsonify({"error": "Refresh time is required"}), 400
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
            return jsonify({"error": "Failed to add to playlist"}), 500

        device_config.write_config()
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    return jsonify({"success": True, "message": "Scheduled refresh configured."})

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
        return jsonify({"error": "Playlist name is required"}), 400
    if not start_time or not end_time:
        return jsonify({"error": "Start time and End time are required"}), 400

    try:
        playlist = playlist_manager.get_playlist(playlist_name)
        if playlist:
            return jsonify({"error": f"Playlist with name '{playlist_name}' already exists"}), 400

        result = playlist_manager.add_playlist(playlist_name, start_time, end_time)
        if not result:
            return jsonify({"error": "Failed to create playlist"}), 500

        # save changes to device config file
        device_config.write_config()

    except Exception as e:
        logger.exception("EXCEPTION CAUGHT: " + str(e))
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

    return jsonify({"success": True, "message": "Created new Playlist!"})


@playlist_bp.route('/update_playlist/<string:playlist_name>', methods=['PUT'])
def update_playlist(playlist_name):
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = device_config.get_playlist_manager()

    data = request.get_json()

    new_name = data.get("new_name")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    if not new_name or not start_time or not end_time:
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    playlist = playlist_manager.get_playlist(playlist_name)
    if not playlist:
        return jsonify({"error": f"Playlist '{playlist_name}' does not exist"}), 400

    result = playlist_manager.update_playlist(playlist_name, new_name, start_time, end_time)
    if not result:
        return jsonify({"error": "Failed to delete playlist"}), 500
    device_config.write_config()

    return jsonify({"success": True, "message": f"Updated playlist '{playlist_name}'!"})

@playlist_bp.route('/delete_playlist/<string:playlist_name>', methods=['DELETE'])
def delete_playlist(playlist_name):
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = device_config.get_playlist_manager()

    if not playlist_name:
        return jsonify({"error": f"Playlist name is required"}), 400

    playlist = playlist_manager.get_playlist(playlist_name)
    if not playlist:
        return jsonify({"error": f"Playlist '{playlist_name}' does not exist"}), 400

    # Delete all images associated with plugin instances in this playlist
    from blueprints.plugin import _delete_plugin_instance_images
    for plugin_instance in playlist.plugins:
        _delete_plugin_instance_images(device_config, plugin_instance)

    playlist_manager.delete_playlist(playlist_name)
    device_config.write_config()

    return jsonify({"success": True, "message": f"Deleted playlist '{playlist_name}'!"})


@playlist_bp.route('/rename_plugin_instance', methods=['PUT'])
def rename_plugin_instance():
    """Rename a plugin instance within a playlist.

    Expects JSON: { playlist_name, plugin_id, old_name, new_name }
    """
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = device_config.get_playlist_manager()

    data = request.get_json() or {}
    playlist_name = data.get('playlist_name')
    plugin_id = data.get('plugin_id')
    old_name = data.get('old_name')
    new_name = data.get('new_name')

    if not playlist_name or not plugin_id or not old_name or not new_name:
        return jsonify({"error": "Missing required fields"}), 400

    # basic validation: allow alphanumeric, spaces (Unicode-aware)
    try:
        import unicodedata
        def _normalize(s):
            return unicodedata.normalize('NFC', (s or "").strip())
    except Exception:
        def _normalize(s):
            return (s or "").strip()

    if not all((ch.isalpha() or ch.isspace() or ch.isnumeric()) for ch in _normalize(new_name)):
        return jsonify({"error": "Instance name can only contain alphanumeric characters and spaces"}), 400

    playlist = playlist_manager.get_playlist(playlist_name)
    if not playlist:
        return jsonify({"error": "Playlist not found"}), 400

    # Find plugin instances using normalized comparison to handle accented characters
    def _find_plugin(playlist_obj, plugin_id_val, name_val):
        for p in playlist_obj.plugins:
            if p.plugin_id == plugin_id_val and _normalize(p.name) == _normalize(name_val):
                return p
        return None

    existing = _find_plugin(playlist, plugin_id, new_name)
    plugin_instance = _find_plugin(playlist, plugin_id, old_name)

    # Add diacritics-insensitive fallback matching for old instance name
    def _remove_diacritics(s):
        try:
            import unicodedata
            nkfd = unicodedata.normalize('NFKD', s)
            return ''.join(ch for ch in nkfd if not unicodedata.combining(ch))
        except Exception:
            return s

    if not plugin_instance:
        base_old = _remove_diacritics(_normalize(old_name)).lower()
        candidates = [p for p in playlist.plugins if p.plugin_id == plugin_id and _remove_diacritics(_normalize(p.name)).lower() == base_old]
        if len(candidates) == 1:
            plugin_instance = candidates[0]
        elif len(candidates) > 1:
            # Ambiguous match: do not guess — return an error listing matches
            matched = [p.name for p in candidates]
            return jsonify({
                "error": f"Ambiguous plugin instance name '{old_name}'",
                "matches": matched
            }), 400

    if not plugin_instance:
        # collect existing instance names for this plugin to help debugging
        existing_names = [p.name for p in playlist.plugins if p.plugin_id == plugin_id]
        return jsonify({"error": f"Plugin instance '{old_name}' not found", "existing_instances": existing_names}), 400

    # If an existing instance with the new name exists and it's not the same instance, reject
    if existing and existing is not plugin_instance:
        return jsonify({"error": f"Plugin instance '{new_name}' already exists"}), 400

    # Also enforce global uniqueness across all playlists, consistent with add_plugin / plugin_page
    global_existing = playlist_manager.find_plugin(plugin_id, new_name)
    if global_existing and global_existing is not plugin_instance:
        return jsonify({"error": f"Plugin instance '{new_name}' already exists"}), 400

    # rename image file if present — perform filesystem update first, then persist
    try:
        old_image = plugin_instance.get_image_path()

        # compute new image path without mutating the persistent object yet
        original_name = plugin_instance.name
        try:
            plugin_instance.name = new_name
            new_image = plugin_instance.get_image_path()
        finally:
            # revert to original in-memory name until filesystem operations succeed
            plugin_instance.name = original_name

        plugin_image_dir = device_config.plugin_image_dir
        old_path = os.path.join(plugin_image_dir, old_image)
        new_path = os.path.join(plugin_image_dir, new_image)

        if os.path.exists(old_path):
            # fail early if target already exists to avoid overwriting
            if os.path.exists(new_path):
                return jsonify({"error": f"Target image file already exists: {new_image}"}), 400

            try:
                os.rename(old_path, new_path)
            except OSError as e:
                # handle cross-device rename by copying then removing
                import errno, shutil
                if getattr(e, 'errno', None) == errno.EXDEV:
                    try:
                        shutil.copy2(old_path, new_path)
                        os.remove(old_path)
                    except Exception:
                        logger.exception(f"Failed to copy plugin image {old_path} -> {new_path}")
                        return jsonify({"error": "Failed to rename plugin image file"}), 500
                else:
                    logger.exception(f"Failed to rename plugin image {old_path} -> {new_path}")
                    return jsonify({"error": "Failed to rename plugin image file"}), 500

        # filesystem update succeeded (or there was no image) — now update in-memory name and persist
        plugin_instance.name = new_name
        device_config.write_config()
    except Exception as e:
        logger.exception("EXCEPTION CAUGHT: " + str(e))
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

    return jsonify({"success": True, "message": f"Renamed '{old_name}' -> '{new_name}'"})

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

    # Define formatting
    time_format = "%I:%M %p"  # Example: 04:30 PM
    month_day_format = "%b %d at " + time_format  # Example: Feb 12 at 04:30 PM

    # Determine relative time string
    if diff_seconds < 120:
        return "just now"
    elif diff_minutes < 60:
        return f"{int(diff_minutes)} minutes ago"
    elif dt.date() == now.date():
        return "today at " + dt.strftime(time_format).lstrip("0")
    elif dt.date() == (now.date() - timedelta(days=1)):
        return "yesterday at " + dt.strftime(time_format).lstrip("0")
    else:
        return dt.strftime(month_day_format).replace(" 0", " ")  # Removes leading zero in day
