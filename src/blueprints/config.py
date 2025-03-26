import logging

from flask import Blueprint, request, jsonify, current_app, render_template, redirect, url_for
from utils.wifi import close_hotspot, connect_to_wifi, is_connected, open_hotspot
from utils.app_utils import get_ip_address, generate_startup_image
from inkypi import display_manager

logger = logging.getLogger(__name__)

config_bp = Blueprint("config", __name__)

@config_bp.route('/config')
def config_page():
    device_config = current_app.config['DEVICE_CONFIG']
    return render_template('config.html', device_settings=device_config.get_config())

@config_bp.route('/save_config', methods=['POST'])
def save_config():
    device_config = current_app.config['DEVICE_CONFIG']

    try:
        form_data = request.form.to_dict()

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
        connect_to_wifi(ssid, form_data.get("password"))
        if is_connected():
            device_config.update_config(config)
            if device_config.get_config("startup") is True:
                logger.info("Startup flag is set, displaying startup image")
                img = generate_startup_image(device_config.get_resolution())
                display_manager.display_image(img)
                device_config.update_value("startup", False, write=True)
            return jsonify({"success": "Connection to wifi established", "ip": get_ip_address() }), 500
        else:
            open_hotspot()
            return jsonify({"error": "Connection to wifi failed!"}), 500
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500