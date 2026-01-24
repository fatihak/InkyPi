from flask import Blueprint, request, jsonify, current_app, render_template
import os
import re
import logging

logger = logging.getLogger(__name__)
apikeys_bp = Blueprint("apikeys", __name__)

# Path to .env file
def get_env_path():
    """Get path to .env file in the project root."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(base_dir, '.env')


def parse_env_file(filepath):
    """Parse .env file and return list of (key, value) tuples."""
    entries = []
    if not os.path.exists(filepath):
        return entries
    
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                # Parse KEY=VALUE
                match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
                if match:
                    key = match.group(1)
                    value = match.group(2)
                    # Remove quotes if present
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    entries.append((key, value))
    except Exception as e:
        logger.error(f"Error parsing .env file: {e}")
    
    return entries


def write_env_file(filepath, entries):
    """Write entries to .env file."""
    try:
        with open(filepath, 'w') as f:
            f.write("# InkyPi API Keys and Secrets\n")
            f.write("# Managed via web interface\n\n")
            for key, value in entries:
                # Quote values with spaces or special characters
                if ' ' in value or '"' in value or "'" in value:
                    value = f'"{value}"'
                f.write(f"{key}={value}\n")
        return True
    except Exception as e:
        logger.error(f"Error writing .env file: {e}")
        return False


def mask_value(value):
    """Mask API key value for display, showing only first/last few chars."""
    if not value:
        return ""
    if len(value) <= 8:
        return "●" * len(value)
    return value[:4] + "●" * (len(value) - 8) + value[-4:]


@apikeys_bp.route('/api-keys')
def apikeys_page():
    """Render API keys management page."""
    env_path = get_env_path()
    entries = parse_env_file(env_path)
    
    # Prepare entries for template: list of dicts with key, masked, value
    template_entries = [
        {"key": key, "masked": mask_value(value), "value": value}
        for key, value in entries
    ]
    
    return render_template(
        'apikeys.html',
        entries=template_entries,
        env_exists=os.path.exists(env_path)
    )


@apikeys_bp.route('/api-keys/save', methods=['POST'])
def save_apikeys():
    """Save API keys to .env file."""
    try:
        data = request.get_json()
        entries = data.get('entries', [])
        
        # Validate entries
        valid_entries = []
        for entry in entries:
            key = entry.get('key', '').strip()
            value = entry.get('value', '').strip()
            
            if not key:
                continue
            
            # Validate key format
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
                return jsonify({"error": f"Invalid key format: {key}"}), 400
            
            valid_entries.append((key, value))
        
        env_path = get_env_path()
        
        if write_env_file(env_path, valid_entries):
            # Reload environment variables
            for key, value in valid_entries:
                os.environ[key] = value
            
            return jsonify({
                "success": True,
                "message": f"Saved {len(valid_entries)} API key(s). Some plugins may require restart to pick up changes."
            })
        else:
            return jsonify({"error": "Failed to write .env file"}), 500
            
    except Exception as e:
        logger.error(f"Error saving API keys: {e}")
        return jsonify({"error": str(e)}), 500

