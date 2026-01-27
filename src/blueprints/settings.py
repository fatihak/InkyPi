from flask import Blueprint, request, jsonify, current_app, render_template, Response
from utils.time_utils import calculate_seconds
from datetime import datetime, timedelta
import os
import pytz
import logging
import io
from buttons import ButtonID, PressType

# Try to import cysystemd for journal reading (Linux only)
try:
    from cysystemd.reader import JournalReader, JournalOpenMode, Rule
    JOURNAL_AVAILABLE = True
except ImportError:
    JOURNAL_AVAILABLE = False
    # Define dummy classes for when cysystemd is not available
    class JournalOpenMode:
        SYSTEM = None
    class Rule:
        pass
    class JournalReader:
        def __init__(self, *args, **kwargs):
            pass


logger = logging.getLogger(__name__)
settings_bp = Blueprint("settings", __name__)

@settings_bp.route('/settings')
def settings_page():
    device_config = current_app.config['DEVICE_CONFIG']
    timezones = sorted(pytz.all_timezones_set)
    display_type = device_config.get_config("display_type", default="inky")
    # Check if display has known default button pins
    is_inky_display = display_type in ("inky", "mock")
    return render_template(
        'settings.html', 
        device_settings=device_config.get_config(), 
        timezones=timezones,
        is_inky_display=is_inky_display
    )

@settings_bp.route('/save_settings', methods=['POST'])
def save_settings():
    device_config = current_app.config['DEVICE_CONFIG']

    try:
        form_data = request.form.to_dict()

        unit, interval, time_format = form_data.get('unit'), form_data.get("interval"), form_data.get("timeFormat")
        if not unit or unit not in ["minute", "hour"]:
            return jsonify({"error": "Plugin cycle interval unit is required"}), 400
        if not interval or not interval.isnumeric():
            return jsonify({"error": "Refresh interval is required"}), 400
        if not form_data.get("timezoneName"):
            return jsonify({"error": "Time Zone is required"}), 400
        if not time_format or time_format not in ["12h", "24h"]:
            return jsonify({"error": "Time format is required"}), 400
        previous_interval_seconds = device_config.get_config("plugin_cycle_interval_seconds")
        plugin_cycle_interval_seconds = calculate_seconds(int(interval), unit)
        if plugin_cycle_interval_seconds > 86400 or plugin_cycle_interval_seconds <= 0:
            return jsonify({"error": "Plugin cycle interval must be less than 24 hours"}), 400

        settings = {
            "name": form_data.get("deviceName"),
            "orientation": form_data.get("orientation"),
            "inverted_image": form_data.get("invertImage"),
            "log_system_stats": form_data.get("logSystemStats"),
            "buttons_enabled": form_data.get("buttonsEnabled") == "on",
            "show_buttons": form_data.get("showButtons") == "on",
            "timezone": form_data.get("timezoneName"),
            "time_format": form_data.get("timeFormat"),
            "plugin_cycle_interval_seconds": plugin_cycle_interval_seconds,
            "image_settings": {
                "saturation": float(form_data.get("saturation", "1.0")),
                "brightness": float(form_data.get("brightness", "1.0")),
                "sharpness": float(form_data.get("sharpness", "1.0")),
                "contrast": float(form_data.get("contrast", "1.0"))
            }
        }
        
        # Handle GPIO button pins if provided
        gpio_a = form_data.get("gpio_a")
        gpio_b = form_data.get("gpio_b")
        gpio_c = form_data.get("gpio_c")
        gpio_d = form_data.get("gpio_d")
        
        if gpio_a and gpio_b and gpio_c and gpio_d:
            try:
                settings["button_pins"] = {
                    "A": int(gpio_a),
                    "B": int(gpio_b),
                    "C": int(gpio_c),
                    "D": int(gpio_d)
                }
            except ValueError:
                pass  # Keep existing pins if invalid values
        
        # Handle button actions
        button_actions = {}
        for btn in ['A', 'B', 'C', 'D']:
            for press_type in ['short', 'double', 'long']:
                key = f"action_{btn}_{press_type}"
                value = form_data.get(key, "")
                if value:  # Only store non-empty values
                    button_actions[f"{btn}_{press_type}"] = value
        
        settings["button_actions"] = button_actions
        
        device_config.update_config(settings)

        if plugin_cycle_interval_seconds != previous_interval_seconds:
            # wake the background thread up to signal interval config change
            refresh_task = current_app.config['REFRESH_TASK']
            refresh_task.signal_config_change()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    return jsonify({"success": True, "message": "Saved settings."})

@settings_bp.route('/shutdown', methods=['POST'])
def shutdown():
    data = request.get_json() or {}
    if data.get("reboot"):
        logger.info("Reboot requested")
        os.system("sudo reboot")
    else:
        logger.info("Shutdown requested")
        os.system("sudo shutdown -h now")
    return jsonify({"success": True})

@settings_bp.route('/download-logs')
def download_logs():
    try:
        buffer = io.StringIO()
        
        # Get 'hours' from query parameters, default to 2 if not provided or invalid
        hours_str = request.args.get('hours', '2')
        try:
            hours = int(hours_str)
        except ValueError:
            hours = 2
        since = datetime.now() - timedelta(hours=hours)

        if not JOURNAL_AVAILABLE:
            # Return a message when running in development mode without systemd
            buffer.write(f"Log download not available in development mode (cysystemd not installed).\n")
            buffer.write(f"Logs would normally show InkyPi service logs from the last {hours} hours.\n")
            buffer.write(f"\nTo see Flask development logs, check your terminal output.\n")
        else:
            reader = JournalReader()
            reader.open(JournalOpenMode.SYSTEM)
            reader.add_filter(Rule("_SYSTEMD_UNIT", "inkypi.service"))
            reader.seek_realtime_usec(int(since.timestamp() * 1_000_000))

            for record in reader:
                try:
                    ts = datetime.fromtimestamp(record.get_realtime_usec() / 1_000_000)
                    formatted_ts = ts.strftime("%b %d %H:%M:%S")
                except Exception:
                    formatted_ts = "??? ?? ??:??:??"

                data = record.data
                hostname = data.get("_HOSTNAME", "unknown-host")
                identifier = data.get("SYSLOG_IDENTIFIER") or data.get("_COMM", "?")
                pid = data.get("_PID", "?")
                msg = data.get("MESSAGE", "").rstrip()

                # Format the log entry similar to the journalctl default output
                buffer.write(f"{formatted_ts} {hostname} {identifier}[{pid}]: {msg}\n")

        buffer.seek(0)
        # Add date and time to the filename
        now_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"inkypi_{now_str}.log"
        return Response(
            buffer.read(),
            mimetype="text/plain",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        logger.error(f"Error reading logs: {e}")
        return Response(f"Error reading logs: {e}", status=500, mimetype="text/plain")


@settings_bp.route('/button_press', methods=['POST'])
def button_press():
    """Handle button press from web UI. Works on both dev and real device."""
    button_manager = current_app.config.get('BUTTON_MANAGER')
    
    if not button_manager:
        return jsonify({"error": "Hardware buttons are disabled"}), 400
    
    data = request.get_json() or {}
    
    try:
        button_id = ButtonID(data.get("button", "A"))
        press_type = PressType(data.get("press_type", "short"))
    except ValueError as e:
        return jsonify({"error": f"Invalid button or press_type: {e}"}), 400
    
    # Call button manager directly (same logic as physical buttons)
    button_manager._on_button_press(button_id, press_type)
    
    return jsonify({
        "success": True, 
        "button": button_id.value, 
        "press_type": press_type.value
    })


# Display type friendly names
DISPLAY_NAMES = {
    "mock": "Mock Display",
    "inky": "Inky Impression",
}


def format_display_type(display_type: str) -> str:
    """Format display type to be more readable."""
    if display_type in DISPLAY_NAMES:
        return DISPLAY_NAMES[display_type]
    # Waveshare displays (epd5in83_V2 -> EPD 5in83 V2)
    if display_type.startswith("epd"):
        return display_type.upper().replace("_", " ")
    # Fallback: capitalize and replace underscores
    return display_type.replace("_", " ").title()


@settings_bp.route('/system_info')
def system_info():
    """Return system information for the info popover."""
    import platform
    import socket
    
    device_config = current_app.config['DEVICE_CONFIG']
    
    # Basic info
    display_type = device_config.get_config("display_type", default="unknown")
    info = {
        "hostname": socket.gethostname(),
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "platform_version": platform.release(),
        "architecture": platform.machine(),
        "display_type": format_display_type(display_type),
    }
    
    # Get IP address
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        info["ip_address"] = s.getsockname()[0]
        s.close()
    except Exception:
        info["ip_address"] = "Unknown"
    
    # Raspberry Pi model (Linux only)
    try:
        with open("/proc/device-tree/model", "r") as f:
            info["device_model"] = f.read().strip().rstrip('\x00')
    except Exception:
        info["device_model"] = f"{platform.system()} {platform.machine()}"
    
    # OS info (Linux)
    try:
        with open("/etc/os-release", "r") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    info["os_name"] = line.split("=", 1)[1].strip().strip('"')
                    break
    except Exception:
        info["os_name"] = f"{platform.system()} {platform.release()}"
    
    # Uptime (Linux only)
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.read().split()[0])
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            if days > 0:
                info["uptime"] = f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                info["uptime"] = f"{hours}h {minutes}m"
            else:
                info["uptime"] = f"{minutes}m"
    except Exception:
        info["uptime"] = "Unknown"
    
    # Display resolution
    try:
        resolution = device_config.get_resolution()
        info["display_resolution"] = f"{resolution[0]}x{resolution[1]}"
    except Exception:
        info["display_resolution"] = "Unknown"
    
    return jsonify(info)

