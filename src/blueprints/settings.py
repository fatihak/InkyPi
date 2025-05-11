from flask import Blueprint, request, jsonify, current_app, render_template
from utils.time_utils import calculate_seconds
import pytz

settings_bp = Blueprint("settings", __name__)

@settings_bp.route('/settings')
def settings_page():
    device_config = current_app.config['DEVICE_CONFIG']
    timezones = sorted(pytz.all_timezones_set)
    return render_template('settings.html', device_settings=device_config.get_config(), timezones = timezones)

@settings_bp.route('/save_settings', methods=['POST'])
def save_settings():
    device_config = current_app.config['DEVICE_CONFIG']

    try:
        form_data = request.form.to_dict()

        unit, interval = form_data.get('unit'), form_data.get("interval")
        if not unit or unit not in ["minute", "hour"]:
            return jsonify({"error": "Plugin cycle interval unit is required"}), 400
        if not interval or not interval.isnumeric():
            return jsonify({"error": "Refresh interval is required"}), 400
        if not form_data.get("timezoneName"):
            return jsonify({"error": "Time Zone is required"}), 400
        plugin_cycle_interval_seconds = calculate_seconds(int(interval), unit)
        if plugin_cycle_interval_seconds > 86400 or plugin_cycle_interval_seconds <= 0:
            return jsonify({"error": "Plugin cycle interval must be less than 24 hours"}), 400

        settings = {
            "name": form_data.get("deviceName"),
            "orientation": form_data.get("orientation"),
            "timezone": form_data.get("timezoneName"),
            "plugin_cycle_interval_seconds": plugin_cycle_interval_seconds
        }
        device_config.update_config(settings)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    return jsonify({"success": True, "message": "Saved settings."})