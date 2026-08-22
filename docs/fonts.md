# Font Management in InkyPi

InkyPi supports dynamic font discovery, allowing you to add custom fonts simply by placing font files in the fonts directory. This guide explains how fonts work, how to add them, and how to use them in plugins.

## Overview

InkyPi automatically discovers fonts from multiple locations:
- **Global fonts:** `src/static/fonts/` (user/system customizations)
- **Plugin fonts:** `src/plugins/*/fonts/` (plugin-specific fonts)

Fonts are available for both:
- **PIL-based rendering** (plugins that draw directly with Pillow)
- **HTML/CSS rendering** (plugins that use the `render_image()` method)

All discovered fonts are automatically included in the base HTML template (`plugin.html`), making them available to all HTML-rendered plugins. Fonts are discovered in priority order: hardcoded (highest) → global → plugin (lowest).

## Supported Font Formats

- **TrueType Fonts** (`.ttf`) - Fully supported
- **OpenType Fonts** (`.otf`) - Fully supported

Fonts can be placed directly in `src/static/fonts/` or in subdirectories (e.g., `src/static/fonts/MyFonts/`).

## Adding Fonts

### Method 1: Global Fonts (User/System Level)

Place your font files in the `src/static/fonts/` directory:

```bash
src/static/fonts/
├── MyCustomFont.ttf
├── MyCustomFont-Bold.ttf
└── AnotherFont/
    └── AnotherFont-Regular.otf
```

**How it works:**
- InkyPi scans the fonts directory on first use
- Font metadata (family name, weight, style) is extracted from the font files using `fonttools`
- If `fonttools` is not available, metadata is inferred from filenames using naming conventions
- Fonts are automatically merged with built-in fonts
- Global fonts have higher priority than plugin fonts

### Method 2: Plugin Fonts (Plugin-Specific)

Plugins can bundle their own fonts by creating a `fonts/` subdirectory:

```bash
src/plugins/myplugin/
├── fonts/
│   ├── PluginFont.ttf
│   └── PluginFont-Bold.ttf
├── myplugin.py
└── ...
```

**How it works:**
- InkyPi automatically scans all plugin directories for `fonts/` subdirectories
- Plugin fonts are discovered and made available system-wide
- When a plugin is removed, its fonts are automatically removed
- Plugin fonts have lower priority than global fonts (can be overridden)
- Perfect for third-party plugins that bundle fonts

**Naming Conventions (fallback when fonttools unavailable):**
- `FontName-Regular.ttf` → family="FontName", weight="normal"
- `FontName-Bold.ttf` → family="FontName", weight="bold"
- `FontName-Italic.ttf` → family="FontName", style="italic"
- `FontName-BoldItalic.ttf` → family="FontName", weight="bold", style="italic"

### Method 2: Metadata Override (Advanced)

For fonts with unusual naming or when you need to override metadata, create a JSON file next to the font file:

**Example:** `MyFont-Bold.ttf` → `MyFont-Bold.json`

```json
{
    "family": "Custom Font Name",
    "weight": "bold",
    "style": "normal"
}
```

The JSON file takes precedence over automatic extraction.

## Built-in Fonts

InkyPi includes these fonts by default:

- **Jost** (normal, bold)
- **DS-Digital** (normal)
- **Napoli** (normal)
- **Dogica** (normal, bold)

Built-in fonts take precedence over discovered fonts if there are conflicts.

## Using Fonts in Plugins

### HTML/CSS Rendering (render_image)

When using `render_image()` from `BasePlugin`, all fonts are automatically available:

**In your HTML template:**

```html
{% extends "plugin.html" %}

{% block content %}
<div style="font-family: 'MyCustomFont', sans-serif;">
    This text uses MyCustomFont
</div>
{% endblock %}
```

**In your CSS file:**

```css
.my-class {
    font-family: "MyCustomFont", sans-serif;
    font-weight: bold;  /* Uses MyCustomFont-Bold if available */
}
```

**Important:** The base template (`plugin.html`) automatically includes `@font-face` declarations for **all discovered fonts**, so you can use any font family name directly in your CSS without additional setup.

### PIL-based Rendering (get_font)

For plugins that draw directly with Pillow:

```python
from utils.app_utils import get_font

# Get a font by family name
font = get_font("MyCustomFont", font_size=50, font_weight="normal")

# Use in drawing
from PIL import ImageDraw
draw = ImageDraw.Draw(image)
draw.text((x, y), "Hello", font=font, fill="black")
```

**Available weights:**
- `"normal"` (default)
- `"bold"`

If a specific weight isn't available, the function falls back to the first available variant.

### Settings Pages (Font Selection Dropdowns)

To show available fonts in plugin settings:

**1. Override `generate_settings_template()` in your plugin:**

```python
from utils.app_utils import get_fonts

class MyPlugin(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        
        # Get unique font family names
        fonts = get_fonts()
        font_families = sorted(set(f["font_family"] for f in fonts))
        template_params["available_fonts"] = font_families
        
        return template_params
```

**2. Use in your settings template:**

```html
<select name="fontFamily" class="form-input">
    {% for font in available_fonts %}
    <option value="{{ font }}">{{ font }}</option>
    {% endfor %}
</select>
```

**Or with JavaScript (if using dynamic forms):**

```html
<script>
// Get fonts from template
const FONTS = {{ available_fonts|tojson }};

// Use in dropdown
const select = document.createElement('select');
FONTS.forEach(font => {
    const option = document.createElement('option');
    option.value = font;
    option.textContent = font;
    select.appendChild(option);
});
</script>
```

## Font Discovery Process

Fonts are discovered in priority order:

1. **Hardcoded fonts** (`FONT_FAMILIES`) - Highest priority (system fonts)
2. **Global fonts** (`src/static/fonts/`) - Medium priority (user/system customizations)
3. **Plugin fonts** (`src/plugins/*/fonts/`) - Lowest priority (plugin-specific fonts)

**Discovery steps:**
1. **On first access:** InkyPi scans all font directories recursively
2. **Metadata extraction:** Uses `fonttools` to read font file metadata (family name, weight, style)
3. **Fallback:** If `fonttools` unavailable, infers from filename
4. **Override check:** Looks for `.json` metadata files
5. **Merging:** Combines fonts in priority order (higher priority fonts override lower priority)
6. **Caching:** Results are cached for performance

## Troubleshooting

### Font not appearing in plugin

1. **Check font file:** Ensure `.ttf` or `.otf` file exists in `src/static/fonts/` or `src/plugins/{plugin_id}/fonts/`
2. **Restart service:** Font discovery happens on first access; restart InkyPi to refresh
3. **Check logs:** Look for font discovery messages in logs
4. **Verify metadata:** Use a metadata JSON file if font name extraction fails

### Font name incorrect

- **Use metadata override:** Create a `.json` file next to the font file to specify the exact family name
- **Install fonttools:** More accurate metadata extraction: `pip install fonttools`

### Font not loading in HTML

- **Check CSS syntax:** Ensure font-family name matches exactly (case-sensitive)
- **Verify @font-face:** Check browser developer tools to see if `@font-face` declarations are present
- **Check template:** Ensure your HTML extends `plugin.html` or includes the font-face declarations

## Reloading Fonts

To force font rediscovery (e.g., after adding new fonts):

```python
from utils.app_utils import reload_fonts
reload_fonts()
```

Or restart the InkyPi service.

## Best Practices

1. **Use descriptive filenames:** Follow naming conventions for better fallback support
2. **Organize in subdirectories:** Group related fonts in folders
3. **Include variants:** Add bold, italic variants for complete font families
4. **Test both rendering methods:** Verify fonts work in both PIL and HTML rendering
5. **Use metadata files:** For fonts with non-standard naming, use JSON metadata files
6. **Bundle fonts with plugins:** Use `fonts/` subdirectory in plugins for plugin-specific fonts
7. **Consider priority:** Global fonts override plugin fonts, so use global fonts for user customizations

## Technical Details

- **Font discovery:** Lazy-loaded on first access, cached thereafter
- **Discovery locations:**
  - Global fonts: `src/static/fonts/`
  - Plugin fonts: `src/plugins/*/fonts/`
- **Priority order:** Hardcoded → Global → Plugin (higher priority overrides lower)
- **Metadata source:** `fonttools` library (if available) or filename parsing
- **Storage:** Font metadata cached in memory (`_DISCOVERED_FONTS`)
- **Template integration:** All fonts automatically included in `plugin.html` via `font_faces` template variable
- **API functions:**
  - `get_font(font_name, font_size, font_weight)` - Get PIL ImageFont object
  - `get_fonts()` - Get list of all fonts for HTML rendering
  - `reload_fonts()` - Force rediscovery
