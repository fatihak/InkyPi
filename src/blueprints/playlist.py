from flask import Blueprint, request, jsonify, current_app, render_template
from utils.time_utils import calculate_seconds
import json
import os
import logging
from utils.app_utils import resolve_path, handle_request_files
from playlist import PlaylistManager, Playlist, Plugin


logger = logging.getLogger(__name__)
playlist_bp = Blueprint("playlist", __name__)

ALLOWED_FILE_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif'}
FILE_SAVE_DIR = resolve_path(os.path.join("static", "images", "saved"))

@playlist_bp.route('/add_plugin', methods=['POST'])
def add_plugin():
    device_config = current_app.config['DEVICE_CONFIG']
    refresh_task = current_app.config['REFRESH_TASK']
    playlist_manager = current_app.config['PLAYLIST_MANAGER']

    try:
        form_data = request.form.to_dict()
        refresh_settings = json.loads(form_data.pop("refresh_settings"))

        playlist = refresh_settings.get('playlist')
        instance_name = refresh_settings.get('instance_name')
        if not refresh_settings.get('interval') or not refresh_settings["interval"].isnumeric():
            raise RuntimeError("Invalid refresh interval.")
        if not refresh_settings.get('unit') or refresh_settings["unit"] not in ["minute", "hour", "day"]:
            raise RuntimeError("Invalid refresh unit.")
        if not playlist:
            raise RuntimeError("Playlist is required.")
        if not instance_name:
            raise RuntimeError("Instance name is required")

        plugin_settings = form_data

        plugin_settings.update(handle_request_files(request.files))
        refresh_interval_seconds = calculate_seconds(int(refresh_settings.get("interval")), refresh_settings.get("unit"))

        plugin_id = plugin_settings.pop("plugin_id")
        playlist_dict = {
            "plugin_id": plugin_id,
            "interval": refresh_interval_seconds,
            "plugin_settings": plugin_settings,
            "name": instance_name
        }
        playlist_manager.add_plugin_to_playlist(playlist, playlist_dict)

        device_config.update_value("playlist_config", playlist_manager.to_dict())

        # device_config.update_value("refresh_settings", {
        #     "interval": refresh_interval_seconds,
        #     "plugin_settings": plugin_settings
        # })
        # refresh_task.update_refresh_settings()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    return jsonify({"success": True, "message": "Scheduled refresh configured."})

@playlist_bp.route('/playlist')
def playlists():
    playlist_manager = current_app.config['PLAYLIST_MANAGER']

    return render_template('playlist.html', playlist_config=playlist_manager.to_dict())

@playlist_bp.route('/create_playlist', methods=['POST'])
def create_playlist():
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = current_app.config['PLAYLIST_MANAGER']

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
        device_config.update_value("playlist_config", playlist_manager.to_dict())

    except Exception as e:
        logger.exception("EXCEPTION CAUGHT: " + str(e))
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

    return jsonify({"success": True, "message": "Created new Playlist!"})


@playlist_bp.route('/update_playlist/<string:playlist_name>', methods=['PUT'])
def update_playlist(playlist_name):
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = current_app.config['PLAYLIST_MANAGER']

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
    device_config.update_value("playlist_config", playlist_manager.to_dict())

    return jsonify({"success": True, "message": f"Updated playlist '{playlist_name}'!"})

@playlist_bp.route('/delete_playlist/<string:playlist_name>', methods=['DELETE'])
def delete_playlist(playlist_name):
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = current_app.config['PLAYLIST_MANAGER']

    if not playlist_name:
        return jsonify({"error": f"Playlist name is required"}), 400
    
    playlist = playlist_manager.get_playlist(playlist_name)
    if not playlist:
        return jsonify({"error": f"Playlist '{playlist_name}' does not exist"}), 400

    playlist_manager.delete_playlist(playlist_name)
    device_config.update_value("playlist_config", playlist_manager.to_dict())

    return jsonify({"success": True, "message": f"Deleted playlist '{playlist_name}'!"})
