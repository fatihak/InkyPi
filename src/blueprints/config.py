import os

from flask import Blueprint, request, jsonify, current_app, render_template, redirect, url_for
from utils.wifi import close_hotspot, connect_to_wifi, is_connected, open_hotspot

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

        name, ssid = form_data.get('name'), form_data.get('ssid')
        if not name:
            return jsonify({"error": "Device name is required"}), 400
        if not ssid:
            return jsonify({"error": "SSID is required"}), 400

        config = {
            "name": form_data.get("deviceName"),
            "ssid": form_data.get("ssid"),
            "password": form_data.get("password"),
            "installed": True
        }
        close_hotspot()
        connect_to_wifi(ssid, form_data.get("password"))
        if is_connected():
            device_config.update_config(config)
            return redirect(url_for("main"))
        else:
            return jsonify({"error": "Connection to wifi failed!"}), 500
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500