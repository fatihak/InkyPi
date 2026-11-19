"""Accent colour presets for the web UI (Settings > Appearance)."""

DEFAULT_ACCENT = "teal"

# primary/hover: buttons and highlights (white text on top);
# text_light/text_dark: accent-coloured text readable on light/dark backgrounds.
ACCENT_PRESETS = {
    "teal":   {"label": "Teal",   "primary": "#1abc9c", "hover": "#16a085", "text_light": "#0f8f75", "text_dark": "#4fd8b9"},
    "blue":   {"label": "Blue",   "primary": "#2f7bea", "hover": "#1f63c8", "text_light": "#1d5fc4", "text_dark": "#6aa6ff"},
    "indigo": {"label": "Indigo", "primary": "#5b5bd6", "hover": "#4646bd", "text_light": "#4a47c4", "text_dark": "#a5a5ff"},
    "violet": {"label": "Violet", "primary": "#8e44ad", "hover": "#7a3796", "text_light": "#7d3c98", "text_dark": "#c99be3"},
    "pink":   {"label": "Pink",   "primary": "#d6457f", "hover": "#bb3369", "text_light": "#b8336a", "text_dark": "#ff8ab8"},
    "coral":  {"label": "Coral",  "primary": "#e2554f", "hover": "#c8403b", "text_light": "#b93a35", "text_dark": "#ff8a84"},
    "orange": {"label": "Orange", "primary": "#d9661f", "hover": "#bd5412", "text_light": "#a94c0e", "text_dark": "#ffad5c"},
    "green":  {"label": "Green",  "primary": "#219150", "hover": "#1a7742", "text_light": "#1a7742", "text_dark": "#5fd98d"},
    "slate":  {"label": "Slate",  "primary": "#4b5563", "hover": "#374151", "text_light": "#374151", "text_dark": "#b4bdca"},
}


def _rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return ", ".join(str(int(hex_color[i:i + 2], 16)) for i in (0, 2, 4))


def get_accent(name):
    """Preset for name (falls back to the default), with RGB triplets for rgba() use."""
    key = name if name in ACCENT_PRESETS else DEFAULT_ACCENT
    preset = dict(ACCENT_PRESETS[key])
    preset["key"] = key
    preset["rgb"] = _rgb(preset["primary"])
    return preset
