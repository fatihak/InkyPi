from flask import Blueprint, request, jsonify, current_app, render_template, send_from_directory
from plugins.plugin_registry import get_plugin_instance
from utils.app_utils import resolve_path
import os
import logging

logger = logging.getLogger(__name__)
plugin_bp = Blueprint("plugin", __name__)

PLUGINS_DIR = resolve_path("plugins")

@plugin_bp.route('/plugin/<plugin_id>')
def plugin_page(plugin_id):
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = current_app.config['PLAYLIST_MANAGER']

    # Find the plugin by id
    plugin_config = next((plugin for plugin in device_config.get_plugins() if plugin['id'] == plugin_id), None)
    if plugin_config:
        try:
            plugin_instance = get_plugin_instance(plugin_config)
            template_params = plugin_instance.generate_settings_template()

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
