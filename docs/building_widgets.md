# Building InkyPi Widgets

This guide walks you through the process of creating a new widget for InkyPi. Widgets are small overlay elements that can be displayed on top of plugin-generated images, such as date stamps, status indicators, or custom messages.

## What are Widgets?

Widgets are lightweight overlay components that:
- Render on top of the active plugin image
- Can be positioned in any corner of the display
- Support automatic contrast color calculation for readability
- Can be enabled/disabled and reordered through the web UI

## Creating a Widget

### 1. Create a Directory for Your Widget

- Navigate to the `src/widgets` directory.
- Create a new directory named after your widget. The directory name will be the `id` of your widget and should be all lowercase with no spaces. Example:

  ```bash
  mkdir src/widgets/date_widget
  ```

### 2. Create a Python File and Class for the Widget

- Inside your new widget directory, create a Python file with the same name as the directory.
- Define a class in the file that inherits from `BaseWidget`.
- In your new class, implement the `generate_image` function:
    - **Arguments:**
        - `settings`: A dictionary of widget configuration values from the form inputs in the web UI.
        - `device_config`: An instance of the Config class, used to retrieve device configurations such as display resolution or timezone.
    - **Return:** A `PIL.Image` object in RGBA mode (with transparency) that will be overlaid on the main image.
    - **Important:** Crop your image to the actual content size to ensure proper positioning.
    - If there are any issues, raise a `RuntimeError` exception with a clear message.

Example widget implementation:

```python
from widgets.base_widget.base_widget import BaseWidget
from utils.app_utils import get_font
from PIL import Image, ImageDraw
from datetime import datetime
import pytz

class DateWidget(BaseWidget):
    def generate_image(self, settings, device_config):
        # Create transparent overlay
        overlay = Image.new('RGBA', (200, 80), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Get settings
        font_size = int(settings.get('font_size', 18))
        font = get_font("Jost", font_size)
        
        # Get current date
        tz = pytz.timezone(device_config.get_config('timezone', 'UTC'))
        now = datetime.now(tz)
        date_str = now.strftime('%Y-%m-%d')
        
        # Use contrast color if enabled
        use_contrast_color = settings.get('use_contrast_color', False)
        if use_contrast_color:
            text_color = settings.get('contrast_color', '#FFFFFF')
        else:
            text_color = settings.get('text_color', '#FFFFFF')
        
        # Draw text
        draw.text((0, 0), date_str, fill=text_color, font=font)
        
        # Crop to actual text size
        bbox = draw.textbbox((0, 0), date_str, font=font)
        return overlay.crop(bbox)
```

### 3. Create a Settings Template (Optional)

If your widget requires user configuration through the web UI, create a `settings.html` file in your widget directory:

```html
<!-- use_contrast_color checkbox is automatically injected by the base widget template -->
<div class="form-group">
    <label for="font_size" class="form-label">Font Size</label>
    <input type="number" name="font_size" class="form-input" 
           value="{{ plugin_settings.font_size | default(18) }}" 
           min="8" max="48">
</div>

<div class="form-group" id="text-color-group">
    <label for="text_color" class="form-label">Text Color</label>
    <input type="color" name="text_color" class="color-picker" 
           value="{{ plugin_settings.text_color | default('#FFFFFF') }}">
</div>

<script>
    // Hide text color picker when contrast color is enabled
    document.addEventListener('DOMContentLoaded', () => {
        const $textColorGroup = document.getElementById('text-color-group');
        const $contrastCheckbox = document.getElementById('use_contrast_color');
        
        $contrastCheckbox.addEventListener('change', (event) => {
            if (event.target.checked) {
                $textColorGroup.classList.add('hidden');
            } else {
                $textColorGroup.classList.remove('hidden');
            }
        });
    });
</script>
```

### 4. Create a Widget Info File

Create a `widget-info.json` file in your widget directory to register it with InkyPi:

```json
{
    "id": "date_widget",
    "display_name": "Date Widget",
    "description": "Displays current date",
    "class": "DateWidget",
    "repository": "https://github.com/your-username/your-widget-repo"
}
```

- **id**: Must match your directory name
- **display_name**: Display name shown in the web UI (required for widgets)
- **description**: Brief description of what the widget does
- **class**: The name of your Python class
- **repository**: Git URL of the widget repository (leave empty for built-in widgets)

### 5. Override Settings Template Generation (Optional)

If your settings template requires additional variables, override the `generate_settings_template` function:

```python
def generate_settings_template(self):
    template_params = super().generate_settings_template()
    template_params['date_formats'] = ['YYYY-MM-DD', 'DD-MM-YYYY', 'MM-DD-YYYY']
    return template_params
```

## Widget Features

### Automatic Contrast Color

Widgets support automatic contrast color calculation to ensure text is readable against any background:

1. Enable the "Use Contrast Color" checkbox in the widget settings
2. The system will analyze the background where the widget will be placed
3. It automatically chooses black (#000000) or white (#FFFFFF) for optimal contrast
4. The contrast color is passed to your widget in `settings['contrast_color']`

### Positioning and Layout

Widgets can be positioned in any corner of the display:
- **Corners**: top-left, top-right, bottom-left, bottom-right
- **Orientation**: horizontal or vertical
- **Spacing**: Gap between multiple widgets (in pixels)
- **Margin**: Distance from the edge of the display (in pixels)

These settings are configured globally in the Widgets page and apply to all enabled widgets.

### Widget Ordering

When multiple widgets are enabled, they are rendered in the order shown in the "Enabled Widgets" list. You can drag and drop to reorder them in the web UI.

## Best Practices

1. **Keep it Small**: Widgets should be compact overlays, not full-screen images
2. **Use Transparency**: Always use RGBA mode and transparent backgrounds
3. **Crop to Content**: Crop your image to the actual content size for proper positioning
4. **Test Contrast**: Test your widget with both light and dark backgrounds
5. **Performance**: Keep widget generation fast since they're applied on every refresh

## Serving Static Assets

If your widget needs to serve static files (images, CSS, etc.), place them in your widget directory and reference them using the widget asset route:

```html
<img src="{{ url_for('widget.widget_asset', widget_id='your_widget_id', filename='icon.png') }}">
```
