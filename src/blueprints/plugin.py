from flask import Blueprint, request, jsonify, current_app, render_template, send_from_directory
from plugins.plugin_registry import get_plugin_instance
from utils.app_utils import resolve_path, handle_request_files, parse_form
from refresh_task import ManualRefresh, PlaylistRefresh
import json
import os
import logging

logger = logging.getLogger(__name__)
plugin_bp = Blueprint("plugin", __name__)

PLUGINS_DIR = resolve_path("plugins")

@plugin_bp.route('/plugin/<plugin_id>')
def plugin_page(plugin_id):
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = device_config.get_playlist_manager()

    # Find the plugin by id
    plugin_config = device_config.get_plugin(plugin_id)
    if plugin_config:
        try:
            plugin = get_plugin_instance(plugin_config)
            template_params = plugin.generate_settings_template()

            # retrieve plugin instance from the query parameters if updating existing plugin instance
            plugin_instance_name = request.args.get('instance')
            if plugin_instance_name:
                plugin_instance = playlist_manager.find_plugin(plugin_id, plugin_instance_name)
                if not plugin_instance:
                    return jsonify({"error": f"Plugin instance: {plugin_instance_name} does not exist"}), 500

                # add plugin instance settings to the template to prepopulate
                template_params["plugin_settings"] = plugin_instance.settings
                template_params["plugin_instance"] = plugin_instance_name
                template_params["plugin_refresh"] = plugin_instance.refresh

            template_params["playlists"] = playlist_manager.get_playlist_names()
        except Exception as e:
            logger.exception("EXCEPTION CAUGHT: " + str(e))
            return jsonify({"error": f"An error occurred: {str(e)}"}), 500
        return render_template('plugin.html', plugin=plugin_config, **template_params)
    else:
        return "Plugin not found", 404

@plugin_bp.route('/images/<plugin_id>/<path:filename>')
def image(plugin_id, filename):
    return send_from_directory(PLUGINS_DIR, os.path.join(plugin_id, filename))

@plugin_bp.route('/delete_plugin_instance', methods=['POST'])
def delete_plugin_instance():
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = device_config.get_playlist_manager()

    data = request.json
    playlist_name = data.get("playlist_name")
    plugin_id = data.get("plugin_id")
    plugin_instance = data.get("plugin_instance")

    try:
        playlist = playlist_manager.get_playlist(playlist_name)
        if not playlist:
            return jsonify({"success": False, "message": "Playlist not found"}), 400

        result = playlist.delete_plugin(plugin_id, plugin_instance)
        if not result:
            return jsonify({"success": False, "message": "Plugin instance not found"}), 400

        # save changes to device config file
        device_config.write_config()

    except Exception as e:
        logger.exception("EXCEPTION CAUGHT: " + str(e))
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

    return jsonify({"success": True, "message": "Deleted plugin instance."})

@plugin_bp.route('/update_plugin_instance/<string:instance_name>', methods=['PUT'])
def update_plugin_instance(instance_name):
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = device_config.get_playlist_manager()

    try:
        form_data = parse_form(request.form)

        if not instance_name:
            raise RuntimeError("Instance name is required")
        
        plugin_id = form_data.get("plugin_id")
        
        # Get existing plugin instance to check for duplicate filenames
        plugin_instance = playlist_manager.find_plugin(plugin_id, instance_name)
        if not plugin_instance:
            return jsonify({"error": f"Plugin instance: {instance_name} does not exist"}), 500
        
        # For image_upload plugin, check for duplicate filenames
        if plugin_id == "image_upload":
            existing_files = plugin_instance.settings.get('imageFiles[]', [])
            existing_filenames = [os.path.basename(f) for f in existing_files]
            
            # Check for duplicates in new uploads
            duplicates = []
            for key, file in request.files.items(multi=True):
                if key == 'imageFiles[]' and file.filename:
                    filename = os.path.basename(file.filename)
                    if filename in existing_filenames:
                        duplicates.append(filename)
            
            if duplicates:
                return jsonify({"error": f"Duplicate files detected: {', '.join(duplicates)}. These files already exist for this instance."}), 400
        
        plugin_settings = form_data
        plugin_settings.update(handle_request_files(request.files, request.form))

        plugin_id = plugin_settings.pop("plugin_id")
        
        # Handle refresh settings if provided
        refresh_settings_json = plugin_settings.pop("refresh_settings", None)
        refresh_settings = {}
        if refresh_settings_json:
            refresh_settings = json.loads(refresh_settings_json)

        plugin_instance.settings = plugin_settings
        
        # Update refresh settings if provided
        if refresh_settings:
            plugin_instance.refresh = refresh_settings
            
        device_config.write_config()
        
        # Check if this plugin instance is currently active and trigger refresh
        refresh_info = device_config.get_refresh_info()
        if (refresh_info.refresh_type == "Playlist" and 
            refresh_info.plugin_id == plugin_id and 
            refresh_info.plugin_instance == instance_name):
            
            refresh_task = current_app.config['REFRESH_TASK']
            from refresh_task import PlaylistRefresh
            
            # Find the playlist containing this plugin
            for playlist in playlist_manager.playlists:
                if playlist.find_plugin(plugin_id, instance_name):
                    refresh_task.manual_update(PlaylistRefresh(playlist, plugin_instance, force=True))
                    break
                    
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    return jsonify({"success": True, "message": f"Updated plugin instance {instance_name}."})

@plugin_bp.route('/display_plugin_instance', methods=['POST'])
def display_plugin_instance():
    device_config = current_app.config['DEVICE_CONFIG']
    refresh_task = current_app.config['REFRESH_TASK']
    playlist_manager = device_config.get_playlist_manager()

    data = request.json
    playlist_name = data.get("playlist_name")
    plugin_id = data.get("plugin_id")
    plugin_instance_name = data.get("plugin_instance")

    try:
        playlist = playlist_manager.get_playlist(playlist_name)
        if not playlist:
            return jsonify({"success": False, "message": f"Playlist {playlist_name} not found"}), 400

        plugin_instance = playlist.find_plugin(plugin_id, plugin_instance_name)
        if not plugin_instance:
            return jsonify({"success": False, "message": f"Plugin instance '{plugin_instance_name}' not found"}), 400

        refresh_task.manual_update(PlaylistRefresh(playlist, plugin_instance, force=True))
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

    return jsonify({"success": True, "message": "Display updated"}), 200

@plugin_bp.route('/update_now', methods=['POST'])
def update_now():
    device_config = current_app.config['DEVICE_CONFIG']
    refresh_task = current_app.config['REFRESH_TASK']

    try:
        plugin_settings = parse_form(request.form)
        plugin_settings.update(handle_request_files(request.files))
        plugin_id = plugin_settings.pop("plugin_id")

        refresh_task.manual_update(ManualRefresh(plugin_id, plugin_settings))
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

    return jsonify({"success": True, "message": "Display updated"}), 200