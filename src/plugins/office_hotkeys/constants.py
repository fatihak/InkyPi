"""Static configuration for the Office Hotkeys plugin. Stdlib-only — safe to unit-test."""

# Skill levels, ordered easiest -> hardest. Index is the difficulty rank.
LEVELS = ["beginner", "intermediate", "advanced"]

# Category rotation order per app. The dataset must cover every category here.
CATEGORY_ORDER = {
    "excel": [
        "Navigation",
        "Selecting & Editing",
        "Formatting",
        "Formulas & Functions",
        "Rows & Columns",
        "Data (Sort & Filter)",
        "Workbook & Sheets",
        "Pivot Tables",
    ],
    "outlook": [
        "Mail",
        "Navigation",
        "Calendar & People",
        "Compose & Format",
    ],
    "powerpoint": [
        "Slides & Navigation",
        "Editing",
        "Formatting",
        "Slideshow",
    ],
}

# Header label and band colour per app (Spectra-6 e-ink: solid, high-contrast).
APP_THEME = {
    "excel":      {"label": "EXCEL",      "color": "#1a7a3c"},  # green
    "outlook":    {"label": "OUTLOOK",    "color": "#1452b0"},  # blue
    "powerpoint": {"label": "POWERPOINT", "color": "#c0301a"},  # red
}
