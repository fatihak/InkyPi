from quart import Blueprint, current_app, render_template, redirect, url_for

main_bp = Blueprint("main", __name__)

@main_bp.route('/')
async def main_page():
    device_config = current_app.config['DEVICE_CONFIG']
    # if the inkypi is not installed redirect to config page
    if device_config.get_config('installed') is True:
      return await render_template('inky.html', config=device_config.get_config(), plugins=device_config.get_plugins())
    return redirect(url_for('config.config_page'))