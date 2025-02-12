from flask import Blueprint, request, jsonify, current_app, render_template
from utils.time_utils import calculate_seconds
import json
import os
import logging
from utils.app_utils import resolve_path, handle_request_files


logger = logging.getLogger(__name__)
playlist_bp = Blueprint("playlist", __name__)

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
        if not playlist:
            return jsonify({"error": "Playlist name is required"}), 400
        if not instance_name or not instance_name.strip():
            return jsonify({"error": "Instance name is required"}), 400
        if not all(char.isalpha() or char.isspace() for char in instance_name):
            return jsonify({"error": "Instance name can only contain alphanumeric characters and spaces"}), 400
        print(refresh_settings)
        refresh_type = refresh_settings.get('refreshType')
        if not refresh_type or refresh_type not in ["interval", "scheduled"]:
            return jsonify({"error": "Refresh type is required"}), 400

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

        plugin_settings = form_data
        plugin_settings.update(handle_request_files(request.files))

        plugin_id = plugin_settings.pop("plugin_id")
        plugin_dict = {
            "plugin_id": plugin_id,
            "refresh": refresh_config,
            "plugin_settings": plugin_settings,
            "name": instance_name
        }
        playlist_manager.add_plugin_to_playlist(playlist, plugin_dict)

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
