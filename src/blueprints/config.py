import logging
import os

from quart import Blueprint, request, jsonify, current_app, render_template, redirect, url_for

logger = logging.getLogger(__name__)

config_bp = Blueprint("config", __name__)

@config_bp.route('/config')
async def config_page():
    device_config = current_app.config['DEVICE_CONFIG']
    return await render_template('config.html', device_settings=device_config.get_config())

@config_bp.route('/save_config', methods=['POST'])
async def save_config():
    device_config = current_app.config['DEVICE_CONFIG']

    try:
        form_data = await request.form
        form_data = form_data.to_dict()

        name, ssid = form_data.get('deviceName'), form_data.get('ssid')
        if not name:
            return jsonify({"error": "Device name is required"}), 400
        if not ssid:
            return jsonify({"error": "SSID is required"}), 400

        config = {
            "name": name,
            "ssid": ssid,
            "password": form_data.get("password"),
            "installed": True
        }
        device_config.update_config(config)
        return jsonify({"success": True, "message": "Connection to wifi established" })
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@config_bp.route('/reboot', methods=['GET'])
def reboot():
    os.system("sudo shutdown -r now")
    return jsonify({"success": True, "message": "Rebooting"})