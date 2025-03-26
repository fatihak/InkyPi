from flask import Blueprint, request, jsonify, current_app, render_template, redirect, url_for

main_bp = Blueprint("main", __name__)

@main_bp.route('/')
def main_page():
    device_config = current_app.config['DEVICE_CONFIG']
    if device_config.get_config('installed') is True:
      return render_template('inky.html', config=device_config.get_config(), plugins=device_config.get_plugins())
    return redirect(url_for('config.config_page'))