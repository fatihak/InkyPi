from flask import Blueprint, request, jsonify, current_app, render_template
from werkzeug.utils import secure_filename
import os
import json
import logging
import subprocess
import shutil
import tempfile
import zipfile
import tarfile

logger = logging.getLogger(__name__)
plugin_manager_bp = Blueprint("plugin_manager", __name__)

ALLOWED_ARCHIVE_EXTENSIONS = {'.zip', '.tar.gz', '.tgz', '.tar'}

def get_plugins_dir():
    """Get the plugins directory path."""
    from utils.app_utils import resolve_path
    return resolve_path("plugins")

def validate_plugin_info(plugin_dir):
    """Validate that plugin-info.json exists and is valid."""
    plugin_info_path = os.path.join(plugin_dir, "plugin-info.json")

    if not os.path.exists(plugin_info_path):
        raise ValueError("plugin-info.json not found")

    try:
        with open(plugin_info_path, 'r') as f:
            plugin_info = json.load(f)

        required_fields = ['display_name', 'id', 'class']
        for field in required_fields:
            if field not in plugin_info:
                raise ValueError(f"Missing required field in plugin-info.json: {field}")

        return plugin_info
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON in plugin-info.json")

def install_requirements(plugin_dir, venv_path=None):
    """Install requirements.txt if it exists."""
    requirements_file = os.path.join(plugin_dir, "requirements.txt")

    if not os.path.exists(requirements_file):
        logger.info("No requirements.txt found, skipping dependency install")
        return True

    logger.info("Installing dependencies from requirements.txt...")

    try:
        # Determine venv path
        if venv_path is None:
            # Try to find venv in standard locations
            base_dir = os.path.dirname(os.path.dirname(plugin_dir))
            possible_venvs = [
                os.path.join(base_dir, 'venv'),
                os.path.join(base_dir, '.venv'),
            ]
            for venv in possible_venvs:
                if os.path.exists(venv):
                    venv_path = venv
                    break

        if venv_path and os.path.exists(venv_path):
            pip_executable = os.path.join(venv_path, 'bin', 'pip')
        else:
            # Fallback to system pip
            pip_executable = 'pip3'

        result = subprocess.run(
            [pip_executable, 'install', '-r', requirements_file],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode != 0:
            logger.error(f"Failed to install requirements: {result.stderr}")
            raise RuntimeError(f"Failed to install requirements: {result.stderr}")

        logger.info("Dependencies installed successfully")
        return True

    except subprocess.TimeoutExpired:
        raise RuntimeError("Installation timed out after 5 minutes")
    except Exception as e:
        logger.exception(f"Error installing requirements: {e}")
        raise RuntimeError(f"Error installing requirements: {str(e)}")

def install_plugin_from_git(plugin_id, repo_url):
    """
    Install a plugin from a Git repository.
    Returns: (success: bool, message: str, plugin_info: dict or None)
    """
    plugins_dir = get_plugins_dir()
    dest_dir = os.path.join(plugins_dir, plugin_id)

    # Validate plugin_id
    if not plugin_id or not plugin_id.replace('_', '').replace('-', '').isalnum():
        raise ValueError("Invalid plugin_id. Use only alphanumeric characters, hyphens, and underscores")

    # Check if plugin already exists
    if os.path.exists(dest_dir):
        raise ValueError(f"Plugin '{plugin_id}' already exists. Remove it first.")

    logger.info(f"Installing plugin '{plugin_id}' from {repo_url}")

    try:
        # Create temporary directory for clone
        os.makedirs(dest_dir, exist_ok=True)

        # Clone repository with sparse checkout
        logger.info("Cloning repository...")
        subprocess.run(
            ['git', 'clone', '--depth', '1', '--filter=blob:none', '--sparse', repo_url, dest_dir],
            capture_output=True,
            text=True,
            check=True,
            timeout=120
        )

        # Get default branch
        result = subprocess.run(
            ['git', '-C', dest_dir, 'symbolic-ref', '--short', 'HEAD'],
            capture_output=True,
            text=True
        )
        default_branch = result.stdout.strip() or 'main'

        # Check if plugin folder exists in repo
        result = subprocess.run(
            ['git', '-C', dest_dir, 'ls-tree', '--name-only', default_branch],
            capture_output=True,
            text=True,
            check=True
        )

        if plugin_id not in result.stdout.split('\n'):
            raise ValueError(f"Plugin folder '{plugin_id}' not found in repository")

        # Sparse checkout the plugin folder
        subprocess.run(
            ['git', '-C', dest_dir, 'sparse-checkout', 'set', plugin_id],
            capture_output=True,
            text=True,
            check=True
        )

        # Move plugin files to root of dest_dir
        plugin_subdir = os.path.join(dest_dir, plugin_id)
        if os.path.exists(plugin_subdir):
            for item in os.listdir(plugin_subdir):
                shutil.move(os.path.join(plugin_subdir, item), dest_dir)
            os.rmdir(plugin_subdir)

        # Validate plugin
        plugin_info = validate_plugin_info(dest_dir)

        # Install requirements
        install_requirements(dest_dir)

        logger.info(f"Plugin '{plugin_id}' installed successfully")
        return True, f"Plugin '{plugin_info['display_name']}' installed successfully", plugin_info

    except subprocess.CalledProcessError as e:
        # Clean up on failure
        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)
        error_msg = e.stderr if hasattr(e, 'stderr') else str(e)
        logger.error(f"Git error: {error_msg}")
        raise RuntimeError(f"Git error: {error_msg}")
    except Exception as e:
        # Clean up on failure
        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)
        raise

def install_plugin_from_archive(archive_file):
    """
    Install a plugin from an uploaded archive file.
    Returns: (success: bool, message: str, plugin_info: dict or None)
    """
    plugins_dir = get_plugins_dir()

    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        archive_path = os.path.join(temp_dir, secure_filename(archive_file.filename))
        archive_file.save(archive_path)

        # Extract archive
        try:
            if zipfile.is_zipfile(archive_path):
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
            elif tarfile.is_tarfile(archive_path):
                with tarfile.open(archive_path, 'r:*') as tar_ref:
                    tar_ref.extractall(temp_dir)
            else:
                raise ValueError("Unsupported archive format. Use ZIP or TAR.GZ")
        except Exception as e:
            raise ValueError(f"Failed to extract archive: {str(e)}")

        # Find plugin-info.json
        plugin_info_path = None
        plugin_root = None

        for root, dirs, files in os.walk(temp_dir):
            if 'plugin-info.json' in files:
                plugin_info_path = os.path.join(root, 'plugin-info.json')
                plugin_root = root
                break

        if not plugin_info_path:
            raise ValueError("plugin-info.json not found in archive")

        # Validate and get plugin info
        plugin_info = validate_plugin_info(plugin_root)
        plugin_id = plugin_info['id']

        # Check if plugin already exists
        dest_dir = os.path.join(plugins_dir, plugin_id)
        if os.path.exists(dest_dir):
            raise ValueError(f"Plugin '{plugin_id}' already exists. Remove it first.")

        # Copy plugin to plugins directory
        shutil.copytree(plugin_root, dest_dir)

        # Install requirements
        install_requirements(dest_dir)

        logger.info(f"Plugin '{plugin_id}' installed successfully from archive")
        return True, f"Plugin '{plugin_info['display_name']}' installed successfully", plugin_info

def remove_plugin(plugin_id):
    """
    Remove an installed plugin.
    Returns: (success: bool, message: str)
    """
    plugins_dir = get_plugins_dir()
    plugin_dir = os.path.join(plugins_dir, plugin_id)

    # Prevent removing base_plugin
    if plugin_id == 'base_plugin':
        raise ValueError("Cannot remove base_plugin")

    # Check if plugin exists
    if not os.path.exists(plugin_dir):
        raise ValueError(f"Plugin '{plugin_id}' not found")

    # Check if plugin-info.json indicates it's a builtin plugin
    try:
        plugin_info_path = os.path.join(plugin_dir, "plugin-info.json")
        if os.path.exists(plugin_info_path):
            with open(plugin_info_path, 'r') as f:
                plugin_info = json.load(f)

            # Only allow removing third-party plugins (those with repository field)
            if not plugin_info.get('repository'):
                raise ValueError(f"Cannot remove builtin plugin '{plugin_id}'")
    except Exception as e:
        logger.warning(f"Error reading plugin-info.json: {e}")

    # Remove plugin directory
    try:
        shutil.rmtree(plugin_dir)
        logger.info(f"Plugin '{plugin_id}' removed successfully")
        return True, f"Plugin '{plugin_id}' removed successfully"
    except Exception as e:
        logger.exception(f"Error removing plugin: {e}")
        raise RuntimeError(f"Failed to remove plugin: {str(e)}")

def update_plugin(plugin_id):
    """
    Update an installed plugin from its Git repository.
    Returns: (success: bool, message: str)
    """
    plugins_dir = get_plugins_dir()
    plugin_dir = os.path.join(plugins_dir, plugin_id)

    # Check if plugin exists
    if not os.path.exists(plugin_dir):
        raise ValueError(f"Plugin '{plugin_id}' not found")

    # Read plugin-info.json to check if it's a third-party plugin
    plugin_info_path = os.path.join(plugin_dir, "plugin-info.json")
    if not os.path.exists(plugin_info_path):
        raise ValueError(f"Plugin '{plugin_id}' has no plugin-info.json")

    try:
        with open(plugin_info_path, 'r') as f:
            plugin_info = json.load(f)
    except json.JSONDecodeError:
        raise ValueError(f"Invalid plugin-info.json for '{plugin_id}'")

    # Check if plugin is third-party (has repository field)
    if not plugin_info.get('repository'):
        raise ValueError(f"Cannot update builtin plugin '{plugin_id}'")

    # Check if plugin directory is a git repository
    git_dir = os.path.join(plugin_dir, '.git')
    if not os.path.exists(git_dir):
        raise ValueError(f"Plugin '{plugin_id}' is not a git repository. Cannot update.")

    logger.info(f"Updating plugin '{plugin_id}' from repository...")

    try:
        # Get current commit hash for comparison
        result = subprocess.run(
            ['git', '-C', plugin_dir, 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        old_commit = result.stdout.strip()

        # Pull latest changes
        result = subprocess.run(
            ['git', '-C', plugin_dir, 'pull'],
            capture_output=True,
            text=True,
            check=True,
            timeout=120
        )

        # Get new commit hash
        result = subprocess.run(
            ['git', '-C', plugin_dir, 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            check=True
        )
        new_commit = result.stdout.strip()

        # Check if there were any updates
        if old_commit == new_commit:
            logger.info(f"Plugin '{plugin_id}' is already up to date")
            return True, f"Plugin '{plugin_info['display_name']}' is already up to date"

        # Validate plugin structure after update
        validate_plugin_info(plugin_dir)

        # Reinstall requirements in case they changed
        install_requirements(plugin_dir)

        logger.info(f"Plugin '{plugin_id}' updated successfully")
        return True, f"Plugin '{plugin_info['display_name']}' updated successfully"

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if hasattr(e, 'stderr') else str(e)
        logger.error(f"Git error during update: {error_msg}")
        raise RuntimeError(f"Failed to update plugin: {error_msg}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Update timed out after 2 minutes")
    except Exception as e:
        logger.exception(f"Error updating plugin: {e}")
        raise

def get_installed_plugins():
    """
    Get list of installed plugins with their info.
    Returns: list of plugin info dictionaries
    """
    plugins_dir = get_plugins_dir()
    plugins = []

    if not os.path.exists(plugins_dir):
        return plugins

    for plugin_id in sorted(os.listdir(plugins_dir)):
        plugin_dir = os.path.join(plugins_dir, plugin_id)

        if not os.path.isdir(plugin_dir) or plugin_id == '__pycache__':
            continue

        plugin_info_path = os.path.join(plugin_dir, "plugin-info.json")

        if os.path.exists(plugin_info_path):
            try:
                with open(plugin_info_path, 'r') as f:
                    plugin_info = json.load(f)

                # Determine plugin type
                if plugin_info.get('repository'):
                    plugin_info['type'] = 'third-party'
                    # Check if it's a git repository (can be updated)
                    git_dir = os.path.join(plugin_dir, '.git')
                    plugin_info['is_git'] = os.path.exists(git_dir)
                else:
                    plugin_info['type'] = 'builtin'
                    plugin_info['is_git'] = False

                plugins.append(plugin_info)
            except Exception as e:
                logger.warning(f"Error reading plugin-info.json for {plugin_id}: {e}")

    return plugins

@plugin_manager_bp.route('/plugins')
def plugins_page():
    """Display the plugin management page."""
    try:
        plugins = get_installed_plugins()
        return render_template('plugin_manager.html', plugins=plugins)
    except Exception as e:
        logger.exception(f"Error loading plugins page: {e}")
        return f"Error: {str(e)}", 500

@plugin_manager_bp.route('/plugins/install/git', methods=['POST'])
def install_git():
    """Install a plugin from a Git repository."""
    try:
        data = request.json
        plugin_id = data.get('plugin_id', '').strip()
        repo_url = data.get('repo_url', '').strip()

        if not plugin_id or not repo_url:
            return jsonify({
                'success': False,
                'message': 'Plugin ID and repository URL are required'
            }), 400

        success, message, plugin_info = install_plugin_from_git(plugin_id, repo_url)

        # Reload plugins in the app
        device_config = current_app.config['DEVICE_CONFIG']
        device_config.plugins_list = device_config.read_plugins_list()

        from plugins.plugin_registry import load_plugins
        load_plugins(device_config.get_plugins())

        return jsonify({
            'success': True,
            'message': message,
            'plugin': plugin_info
        })

    except Exception as e:
        logger.exception(f"Error installing plugin from git: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400

@plugin_manager_bp.route('/plugins/install/upload', methods=['POST'])
def install_upload():
    """Install a plugin from an uploaded archive."""
    try:
        if 'archive' not in request.files:
            return jsonify({
                'success': False,
                'message': 'No archive file provided'
            }), 400

        archive_file = request.files['archive']

        if archive_file.filename == '':
            return jsonify({
                'success': False,
                'message': 'No file selected'
            }), 400

        # Validate file extension
        filename_lower = archive_file.filename.lower()
        if not any(filename_lower.endswith(ext) for ext in ALLOWED_ARCHIVE_EXTENSIONS):
            return jsonify({
                'success': False,
                'message': f'Invalid file type. Allowed: {", ".join(ALLOWED_ARCHIVE_EXTENSIONS)}'
            }), 400

        success, message, plugin_info = install_plugin_from_archive(archive_file)

        # Reload plugins in the app
        device_config = current_app.config['DEVICE_CONFIG']
        device_config.plugins_list = device_config.read_plugins_list()

        from plugins.plugin_registry import load_plugins
        load_plugins(device_config.get_plugins())

        return jsonify({
            'success': True,
            'message': message,
            'plugin': plugin_info
        })

    except Exception as e:
        logger.exception(f"Error installing plugin from upload: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400

@plugin_manager_bp.route('/plugins/update/<plugin_id>', methods=['POST'])
def update(plugin_id):
    """Update an installed plugin."""
    try:
        success, message = update_plugin(plugin_id)

        # Reload plugins in the app
        device_config = current_app.config['DEVICE_CONFIG']
        device_config.plugins_list = device_config.read_plugins_list()

        from plugins.plugin_registry import load_plugins
        load_plugins(device_config.get_plugins())

        return jsonify({
            'success': True,
            'message': message
        })

    except Exception as e:
        logger.exception(f"Error updating plugin: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400

@plugin_manager_bp.route('/plugins/remove/<plugin_id>', methods=['DELETE'])
def remove(plugin_id):
    """Remove an installed plugin."""
    try:
        success, message = remove_plugin(plugin_id)

        # Reload plugins in the app
        device_config = current_app.config['DEVICE_CONFIG']
        device_config.plugins_list = device_config.read_plugins_list()

        from plugins.plugin_registry import load_plugins, PLUGIN_CLASSES
        # Clear the removed plugin from registry
        if plugin_id in PLUGIN_CLASSES:
            del PLUGIN_CLASSES[plugin_id]
        load_plugins(device_config.get_plugins())

        return jsonify({
            'success': True,
            'message': message
        })

    except Exception as e:
        logger.exception(f"Error removing plugin: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400

@plugin_manager_bp.route('/plugins/list', methods=['GET'])
def list_plugins():
    """Get list of installed plugins as JSON."""
    try:
        plugins = get_installed_plugins()
        return jsonify({
            'success': True,
            'plugins': plugins
        })
    except Exception as e:
        logger.exception(f"Error listing plugins: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
