IMAGE_FIT_MODES = {"cover", "contain", "auto"}
IMAGE_FIT_PLUGINS = {"image_album", "image_folder", "image_upload"}


def _migrate_image_fit(settings):
    fit_mode = settings.get("fitMode")
    if fit_mode not in IMAGE_FIT_MODES:
        fit_mode = "contain" if settings.get("padImage") == "true" else "cover"

    settings["fitMode"] = fit_mode
    settings.pop("padImage", None)


PLUGIN_SETTING_MIGRATIONS = {
    plugin_id: (_migrate_image_fit,) for plugin_id in IMAGE_FIT_PLUGINS
}


def migrate_plugin_settings(plugin_id, settings):
    """Apply registered migrations before plugin settings are used."""
    migrations = PLUGIN_SETTING_MIGRATIONS.get(plugin_id)
    if not migrations:
        return settings

    migrated = dict(settings or {})
    for migration in migrations:
        migration(migrated)
    return migrated
