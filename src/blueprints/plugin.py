from flask import Blueprint, request, jsonify, current_app, render_template, send_from_directory, send_file
from plugins.plugin_registry import get_plugin_instance
from utils import eink
from utils.image_utils import apply_image_enhancement
from utils.app_utils import resolve_path, handle_request_files, parse_form
from refresh_task import ManualRefresh, PlaylistRefresh, PreviewRefresh
import io
import json
import os
import logging
from utils.i18n import _
import threading
import shutil
import tempfile
import time
import uuid

logger = logging.getLogger(__name__)
plugin_bp = Blueprint("plugin", __name__)

def _delete_plugin_instance_images(device_config, plugin_instance_obj):
    """Delete all images associated with a plugin instance."""
    # Delete the plugin instance's generated image
    plugin_image_path = os.path.join(device_config.plugin_image_dir, plugin_instance_obj.get_image_path())
    if os.path.exists(plugin_image_path):
        try:
            os.remove(plugin_image_path)
            logger.info(f"Deleted plugin instance image: {plugin_image_path}")
        except Exception as e:
            logger.warning(f"Failed to delete plugin instance image {plugin_image_path}: {e}")

    # Call the plugin's cleanup method to handle plugin-specific resource cleanup
    try:
        plugin_config = device_config.get_plugin(plugin_instance_obj.plugin_id)
        if plugin_config:
            plugin = get_plugin_instance(plugin_config)
            plugin.cleanup(plugin_instance_obj.settings)
    except Exception as e:
        logger.warning(f"Error during plugin cleanup for {plugin_instance_obj.plugin_id}: {e}")

# Removed module-level PLUGINS_DIR - will resolve dynamically in route handlers

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
                    return jsonify({"error": _("Plugin instance '{name}' does not exist", name=plugin_instance_name)}), 500

                # add plugin instance settings to the template to prepopulate
                template_params["plugin_settings"] = plugin_instance.settings
                template_params["plugin_instance"] = plugin_instance_name
                template_params["refresh_settings"] = plugin_instance.refresh

            template_params["playlists"] = playlist_manager.get_playlist_names()
            # Colour rendering: recommended mode for this plugin, global values used as the
            # starting point of manual settings, and whether the display has a known palette
            # (graphics mode and e-ink simulation available)
            template_params["default_colour_mode"] = eink.default_mode(plugin_id)
            template_params["global_image_settings"] = eink.colour_plan(
                plugin_id, {}, device_config.get_config("image_settings"))["enhance"]
            display_manager = current_app.config.get('DISPLAY_MANAGER')
            template_params["has_palette"] = bool(display_manager and display_manager.get_palette())
        except Exception as e:
            logger.exception("EXCEPTION CAUGHT: " + str(e))
            return jsonify({"error": _("An error occurred: {message}", message=str(e))}), 500
        return render_template('plugin.html', plugin=plugin_config, **template_params)
    else:
        return "Plugin not found", 404

@plugin_bp.route('/images/<plugin_id>/<path:filename>')
def image(plugin_id, filename):
    # Resolve plugins directory dynamically
    plugins_dir = resolve_path("plugins")

    # Construct the full path to the plugin's file
    plugin_dir = os.path.join(plugins_dir, plugin_id)

    # Security check to prevent directory traversal
    safe_path = os.path.abspath(os.path.join(plugin_dir, filename))
    if not safe_path.startswith(os.path.abspath(plugins_dir)):
        return "Invalid path", 403

    # Convert to absolute path for send_from_directory
    abs_plugin_dir = os.path.abspath(plugin_dir)

    # Check if the directory and file exist
    if not os.path.isdir(abs_plugin_dir):
        logger.error(f"Plugin directory not found: {abs_plugin_dir}")
        return "Plugin directory not found", 404

    if not os.path.isfile(safe_path):
        logger.error(f"File not found: {safe_path}")
        return "File not found", 404

    # Serve the file from the plugin directory
    return send_from_directory(abs_plugin_dir, filename)

@plugin_bp.route('/plugin_instance_image/<path:playlist_name>/<path:plugin_id>/<path:instance_name>')
def plugin_instance_image(playlist_name, plugin_id, instance_name):
    """Serve the generated image for a plugin instance."""
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = device_config.get_playlist_manager()

    # Find the plugin instance
    playlist = playlist_manager.get_playlist(playlist_name)
    if not playlist:
        return "Playlist not found", 404

    plugin_instance = playlist.find_plugin(plugin_id, instance_name)
    if not plugin_instance:
        return "Plugin instance not found", 404

    # Get the image path
    image_filename = plugin_instance.get_image_path()
    image_path = os.path.join(device_config.plugin_image_dir, image_filename)

    # Check if the image exists
    if not os.path.exists(image_path):
        # Return a placeholder or 404
        return "Image not yet generated", 404

    # Serve the image
    return send_from_directory(device_config.plugin_image_dir, image_filename)

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
            return jsonify({"success": False, "message": _("Playlist not found")}), 400

        # Get the plugin instance to find associated images
        plugin_instance_obj = playlist.find_plugin(plugin_id, plugin_instance)
        if not plugin_instance_obj:
            return jsonify({"success": False, "message": _("Plugin instance not found")}), 400

        # Delete associated images before removing from playlist
        _delete_plugin_instance_images(device_config, plugin_instance_obj)

        result = playlist.delete_plugin(plugin_id, plugin_instance)
        if not result:
            return jsonify({"success": False, "message": _("Plugin instance not found")}), 400

        # save changes to device config file
        device_config.write_config()

    except Exception as e:
        logger.exception("EXCEPTION CAUGHT: " + str(e))
        return jsonify({"error": _("An error occurred: {message}", message=str(e))}), 500

    return jsonify({"success": True, "message": _("Deleted plugin instance.")})

@plugin_bp.route('/update_plugin_instance/<string:instance_name>', methods=['PUT'])
def update_plugin_instance(instance_name):
    device_config = current_app.config['DEVICE_CONFIG']
    playlist_manager = device_config.get_playlist_manager()

    try:
        form_data = parse_form(request.form)

        if not instance_name:
            raise RuntimeError("Instance name is required")

        plugin_id = form_data.pop("plugin_id")
        plugin_instance = playlist_manager.find_plugin(plugin_id, instance_name)
        if not plugin_instance:
            return jsonify({"error": _("Plugin instance '{name}' does not exist", name=instance_name)}), 500

        # Handle refresh settings if provided
        refresh_settings_json = form_data.pop("refresh_settings", None)
        if refresh_settings_json:
            from utils.time_utils import calculate_seconds
            refresh_settings = json.loads(refresh_settings_json)
            refresh_type = refresh_settings.get('refreshType')

            if refresh_type == "interval":
                unit = refresh_settings.get('unit')
                interval = refresh_settings.get('interval')
                if unit and interval:
                    refresh_interval_seconds = calculate_seconds(int(interval), unit)
                    plugin_instance.refresh = {"interval": refresh_interval_seconds}
            elif refresh_type == "scheduled":
                refresh_time = refresh_settings.get('refreshTime')
                if refresh_time:
                    plugin_instance.refresh = {"scheduled": refresh_time}

        # Only update plugin settings if there's actual data (not just refresh settings)
        plugin_settings = form_data
        plugin_settings.update(handle_request_files(request.files, request.form))

        if plugin_settings:  # Only update if there are actual plugin settings
            plugin_instance.settings = plugin_settings

        device_config.write_config()
    except Exception as e:
        return jsonify({"error": _("An error occurred: {message}", message=str(e))}), 500
    return jsonify({"success": True, "message": _("Updated plugin instance '{name}'.", name=instance_name)})

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
            return jsonify({"success": False, "message": _("Playlist '{name}' not found", name=playlist_name)}), 400

        plugin_instance = playlist.find_plugin(plugin_id, plugin_instance_name)
        if not plugin_instance:
            return jsonify({"success": False, "message": _("Plugin instance '{name}' not found", name=plugin_instance_name)}), 400

        refresh_task.manual_update(PlaylistRefresh(playlist, plugin_instance, force=True))
    except Exception as e:
        return jsonify({"error": _("An error occurred: {message}", message=str(e))}), 500

    return jsonify({"success": True, "message": _("Display updated")}), 200

@plugin_bp.route('/update_now', methods=['POST'])
def update_now():
    device_config = current_app.config['DEVICE_CONFIG']
    refresh_task = current_app.config['REFRESH_TASK']
    display_manager = current_app.config['DISPLAY_MANAGER']

    try:
        plugin_settings = parse_form(request.form)
        plugin_settings.update(handle_request_files(request.files))
        plugin_id = plugin_settings.pop("plugin_id")

        # Check if refresh task is running
        if refresh_task.running:
            refresh_task.manual_update(ManualRefresh(plugin_id, plugin_settings))
        else:
            # In development mode, directly update the display
            logger.info("Refresh task not running, updating display directly")
            plugin_config = device_config.get_plugin(plugin_id)
            if not plugin_config:
                return jsonify({"error": _("Plugin '{name}' not found", name=plugin_id)}), 404

            plugin = get_plugin_instance(plugin_config)
            image = plugin.generate_image(plugin_settings, device_config)
            display_manager.display_image(image, image_settings=plugin_config.get("image_settings", []),
                                          colour_plan=eink.colour_plan(plugin_id, plugin_settings,
                                                                       device_config.get_config("image_settings")))

    except Exception as e:
        logger.exception(f"Error in update_now: {str(e)}")
        return jsonify({"error": _("An error occurred: {message}", message=str(e))}), 500

    return jsonify({"success": True, "message": _("Display updated")}), 200


# One preview at a time: each one may start a headless browser on a small device
_preview_lock = threading.Lock()

# The last rendered preview (the plugin's own image, before any colour processing):
# - "Show on the display" sends that exact image instead of rendering again (random
#   images would differ, AI images would be generated twice);
# - changing only the colour rendering (simulation, photo/graphics/manual) reuses it
#   instead of running the plugin again (seconds of headless browser on a Pi).
PREVIEW_KEEP_SECONDS = 600
_last_preview = {}


def _preview_cache_key(plugin_id, plugin_settings):
    content = {k: v for k, v in plugin_settings.items() if k not in eink.RENDER_FIELDS}
    return json.dumps([plugin_id, content], sort_keys=True, default=str)


def _reusable_preview(key):
    if _last_preview.get("key") == key and time.monotonic() - _last_preview["time"] < PREVIEW_KEEP_SECONDS:
        return _last_preview["image"].copy()
    return None


@plugin_bp.route('/preview_image', methods=['POST'])
def preview_image():
    """Renders a plugin with the submitted (unsaved) settings and returns the PNG,
    without touching the e-ink display or any playlist."""
    device_config = current_app.config['DEVICE_CONFIG']
    if not _preview_lock.acquire(blocking=False):
        return jsonify({"error": _("A preview is already being generated, please wait.")}), 429

    preview_dir = None
    try:
        plugin_settings = parse_form(request.form)
        # Existing files sent back by the form are merged with newly uploaded ones. New
        # uploads go to a temporary folder: an unsaved preview must not overwrite an image
        # with the same name that a playlist item uses.
        preview_dir = tempfile.mkdtemp(prefix="inkypi-preview-")
        plugin_settings.update(handle_request_files(request.files, request.form, save_dir=preview_dir))
        plugin_id = plugin_settings.pop("plugin_id", None)

        plugin_config = device_config.get_plugin(plugin_id)
        if not plugin_config:
            return jsonify({"error": _("Plugin '{name}' not found", name=plugin_id)}), 404

        simulate = plugin_settings.pop("simulateDisplay", None) == "true"
        # (new uploads are saved under new temporary paths, so they never match)
        reuse = plugin_settings.pop("reuseRender", None) == "true"
        cache_key = _preview_cache_key(plugin_id, plugin_settings)
        image = _reusable_preview(cache_key) if reuse else None
        reused = image is not None
        if image is None:
            plugin = get_plugin_instance(plugin_config)
            image = plugin.generate_image(plugin_settings, device_config)
            if image is None:
                return jsonify({"error": _("The plugin did not produce an image")}), 500
            _last_preview.clear()
            _last_preview.update(id=uuid.uuid4().hex, key=cache_key, plugin_id=plugin_id,
                                 image=image.copy(), time=time.monotonic())
        # the colour settings of the latest request apply when the preview is displayed
        _last_preview["settings"] = dict(plugin_settings)

        # Shown with the image settings (brightness, contrast...) like on the display, and
        # optionally as the panel will render it (same colour rendering as a real refresh)
        plan = eink.colour_plan(plugin_id, plugin_settings, device_config.get_config("image_settings"))
        image = apply_image_enhancement(image.convert("RGB"), plan["enhance"])
        display_manager = current_app.config.get('DISPLAY_MANAGER')
        palette = display_manager.get_palette() if display_manager else None
        if simulate and palette:
            image = eink.simulate(image, palette, plan["mode"], plan["saturation"])

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        response = send_file(buffer, mimetype="image/png")
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Preview-Id"] = _last_preview["id"]
        response.headers["X-Preview-Reused"] = "1" if reused else "0"
        return response
    except Exception as e:
        logger.exception(f"Error in preview_image: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        if preview_dir:
            shutil.rmtree(preview_dir, ignore_errors=True)
        _preview_lock.release()


@plugin_bp.route('/display_preview', methods=['POST'])
def display_preview():
    """Shows the last previewed image on the display, without rendering it again."""
    device_config = current_app.config['DEVICE_CONFIG']
    refresh_task = current_app.config['REFRESH_TASK']
    preview_id = (request.get_json(silent=True) or {}).get("preview_id")
    preview = dict(_last_preview)
    if not preview_id or preview.get("id") != preview_id or \
            time.monotonic() - preview["time"] > PREVIEW_KEEP_SECONDS:
        return jsonify({"error": _("This preview is no longer available, render it again.")}), 410
    try:
        if refresh_task.running:
            refresh_task.manual_update(PreviewRefresh(preview["plugin_id"], preview["image"],
                                                      preview.get("settings", {})))
        else:
            # In development mode, directly update the display
            plugin_config = device_config.get_plugin(preview["plugin_id"]) or {}
            current_app.config['DISPLAY_MANAGER'].display_image(
                preview["image"].copy(), image_settings=plugin_config.get("image_settings", []),
                colour_plan=eink.colour_plan(preview["plugin_id"], preview.get("settings", {}),
                                             device_config.get_config("image_settings")))
    except Exception as e:
        logger.exception(f"Error in display_preview: {str(e)}")
        return jsonify({"error": _("An error occurred: {message}", message=str(e))}), 500
    return jsonify({"success": True, "message": _("Display updated")}), 200
