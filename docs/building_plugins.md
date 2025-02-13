# Building InkyPi Plugins

This guide walks you through the process of creating a new plugin for InkyPi. 

### 1. Create a Directory for Your Plugin

- Navigate to the `src/plugins` directory.
- Create a new directory named after your plugin. The directory name will be the `id` of your plugin and should be all lowercase with no spaces. Example:

  ```bash
  mkdir plugins/clock
  ```

### 2. Create a Python File and Class for the Plugin

- Inside your new plugin directory, create a Python file with the same name as the directory.
- Define a class in the file that inherits from `BasePlugin`.
- In your new class, implement the `generate_image` function
    - Arguments:
        - `settings`: A dictionary of plugin configuration values from the form inputs in the web UI.
        - `device_config`: An instance of the Config class, used to retrieve device configurations such as display resolution or dotenv keys for any secrets.
    - Return a single `PIL.Image` object to be displayed
    - If there are any issues (e.g., missing configuration options or API keys), raise a `RuntimeError` exception with a clear and concise message to be displayed in the web UI.
- (Optional) If your settings template requires any additional variables, override the default `generate_settings_template` function
    - In this function, call `BasePlugin`'s `generate_settings_template` method to retrieve the default template parameters. Add any extra key-value pairs needed for your template and return the updated dictionary.
    - Example:
        ```python
        def generate_settings_template(self):
            template_params = super().generate_settings_template()
            template_params['custom_template_variable'] = self.get_custom_variable()
            return template_params
        ```
- (Optional) If your plugin needs to cache or store data across refreshes, you can manage this within the `generate_image` function.
    - For example, you can retrieve and update values as follows:
        ```python
        def generate_image(self, settings, device_config):
            # retrieve stored value with a default
            cached_index = settings.get("index", 0)

            # update value for next refresh
            settings["index"] = settings["index"] + 1
        ```

### 3. Create a Settings Template (Optional)

If your plugin requires user configuration through the web UI, you’ll need to define a settings template.
- In your plugin directory, create a `settings.html` file
- Inside this file, define HTML input elements for any settings required by your plugin:
    - The `name` attribute of each input element will be passed as keys in the `settings` argument of the `generate_image` function
- Any template variables added in `generate_settings_template` function will be accessible in the settings template. This is useful for dynamic content, such as populating options in a dropdown menu.
- Ensure the settings template visually matches the style of the existing web UI and other plugin templates for consistency.
- When a plugin is added to a playlist, editing the plugin instance should prepopulate the form with the current settings, and saving changes should update the settings accordingly. 

### 4. Add an Icon for Your Plugin

- Create an `icon.png` file in your plugin’s directory. This will be the icon displayed in the web UI.
    - Ensure the icon visually matches the style of existing icons in the project.

### 5. Register Your Plugin

- Open the `src/plugins/plugins.json` file.
- Add an entry for your plugin using the following structure:
    ```json
    {
        "display_name": "Clock",    # The name shown in the web UI for the plugin.
        "id": "clock",              # A unique identifier for the plugin (use lowercase and avoid spaces)
        "class": "Clock"            # The name of your plugin’s Python class.
    }
    ```

## Test Your Plugin

- Restart the InkyPi service by running
    ```bash
    sudo systemctl restart inkypi.service
    ```
- Test and ensure that your plugin:
    - Loads correctly on service start.
    - Appears under the "Plugins" section in the web UI with it's icon.
    - Settings template is rendered correctly.
    - Generates and displays images with immediate updates and in a playlist.
    - Setting template is prepopulated and saved correctly when editing an existing playlist

## Example Directory Structure

Here’s how your plugin directory should look:

```
plugins/{plugin_id}/
    ├── {plugin_id}.py          # Main plugin script
    ├── icon.png                # Plugin icon
    ├── settings.html           # Optional: Plugin settings page (if applicable)
    └── {other files/resources} # Any additional files or resources used by the plugin
```

## Preopulating forms for Plugin Instances

When a plugin is added to a playlist, a "Plugin Instance" is created, and its settings are stored in the `src/config/device.json` file. These settings can be updated from the playlist page, so the form in settings.html should be prepopulated with the existing settings.

- The `loadPluginSettings` variable should be checked to ensure the settings page is in "edit" mode.
- Plugin settings are accessible via the `pluginSettings` object.
- Example:
    ```JavaScript
    document.addEventListener('DOMContentLoaded', () => {     
        if (loadPluginSettings) {
            # Text Input
            document.getElementById('{textInputElementId}').value = pluginSettings.textInpuElementName || '';

            # Radio
            document.querySelector(`input[name="radioElementName"][value="${pluginSettings.radioElementName}"]`).checked = true;

            # Color Input
            document.getElementById('{colorInputElementId}').value = pluginSettings.colorInputElementName

            ...
        }
    });
    ```