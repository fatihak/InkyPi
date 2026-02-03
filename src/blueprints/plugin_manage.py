"""Blueprint for managing third-party plugins (install/uninstall) from the web UI."""

import os
import subprocess
from urllib.parse import urlparse

from flask import Blueprint, request, jsonify, current_app, render_template
import logging

from config import Config

logger = logging.getLogger(__name__)

plugin_manage_bp = Blueprint("plugin_manage", __name__)


def _project_dir():
    """Project root (parent of src/)."""
    return os.path.dirname(Config.BASE_DIR)


def _cli_script():
    """Path to the inkypi-plugin CLI script."""
    return os.path.join(_project_dir(), "install", "cli", "inkypi-plugin")


def _third_party_plugins():
    """Plugins that have a repository (third-party)."""
    device_config = current_app.config["DEVICE_CONFIG"]
    return [p for p in device_config.get_plugins() if p.get("repository")]


def _validate_install_url(url):
    """Validate URL for install: HTTPS only. Returns (ok, error_message)."""
    if not url or not isinstance(url, str):
        return False, "URL is required"
    url = url.strip()
    if not url:
        return False, "URL is required"
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL"
    if parsed.scheme != "https":
        return False, "Only HTTPS URLs are allowed"
    if not parsed.netloc:
        return False, "Invalid URL host"
    return True, None


@plugin_manage_bp.route("/manage-plugins")
def plugin_manage_page():
    """Render the plugin management page with list of third-party plugins."""
    third_party = _third_party_plugins()
    return render_template("plugin_manage.html", third_party_plugins=third_party)


@plugin_manage_bp.route("/manage-plugins/install", methods=["POST"])
def install_plugin():
    """Install a plugin from a Git repository URL. Uses CLI install-from-url."""
    data = request.get_json() or {}
    url = data.get("url", "")

    ok, err = _validate_install_url(url)
    if not ok:
        return jsonify({"success": False, "error": err}), 400

    cli = _cli_script()
    if not os.path.isfile(cli):
        return jsonify({"success": False, "error": "Plugin CLI not found"}), 500

    project_dir = _project_dir()
    env = {**os.environ, "PROJECT_DIR": project_dir}

    try:
        result = subprocess.run(
            ["bash", cli, "install-from-url", url.strip()],
            env=env,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Install timed out"}), 500
    except Exception as e:
        logger.exception("Plugin install subprocess failed")
        return jsonify({"success": False, "error": str(e)}), 500

    if result.returncode != 0:
        err_msg = result.stderr.strip() or result.stdout.strip() or "Install failed"
        logger.warning("Plugin install failed: %s", err_msg)
        return jsonify({"success": False, "error": err_msg}), 400

    return jsonify({"success": True})


@plugin_manage_bp.route("/manage-plugins/uninstall", methods=["POST"])
def uninstall_plugin():
    """Uninstall a third-party plugin by id. Only allows plugins with repository set."""
    data = request.get_json() or {}
    plugin_id = (data.get("plugin_id") or "").strip()

    if not plugin_id:
        return jsonify({"success": False, "error": "plugin_id is required"}), 400

    third_party = _third_party_plugins()
    allowed_ids = {p["id"] for p in third_party}
    if plugin_id not in allowed_ids:
        return jsonify({"success": False, "error": "Plugin not found or cannot be uninstalled"}), 400

    cli = _cli_script()
    if not os.path.isfile(cli):
        return jsonify({"success": False, "error": "Plugin CLI not found"}), 500

    project_dir = _project_dir()
    env = {**os.environ, "PROJECT_DIR": project_dir}

    try:
        result = subprocess.run(
            ["bash", cli, "uninstall", plugin_id],
            env=env,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Uninstall timed out"}), 500
    except Exception as e:
        logger.exception("Plugin uninstall subprocess failed")
        return jsonify({"success": False, "error": str(e)}), 500

    if result.returncode != 0:
        err_msg = result.stderr.strip() or result.stdout.strip() or "Uninstall failed"
        logger.warning("Plugin uninstall failed: %s", err_msg)
        return jsonify({"success": False, "error": err_msg}), 400

    return jsonify({"success": True})
