#!/usr/bin/env python3
"""List the UI strings marked for translation and check catalogs for missing entries.

Usage: python scripts/extract_ui_strings.py [lang ...]   (default: every catalog)
Strings are marked with _('...') in templates/Python and t('...') in JavaScript.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
PATTERNS = [re.compile(r"""\b_\(\s*(['"])((?:\\.|(?!\1).)*)\1"""),
            re.compile(r"""\bt\(\s*(['"])((?:\\.|(?!\1).)*)\1""")]
SOURCES = ["templates/**/*.html", "blueprints/*.py", "utils/i18n.py", "plugins/*/settings.html",
           # project scripts only (vendor libraries live in the same folder)
           "static/scripts/dark_mode.js", "static/scripts/image_modal.js",
           "static/scripts/refresh_settings_manager.js", "static/scripts/response_modal.js"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def extract():
    found = set(MONTHS)
    for pattern in SOURCES:
        for path in glob.glob(os.path.join(ROOT, pattern), recursive=True):
            text = open(path, encoding="utf-8").read()
            for regex in PATTERNS:
                for match in regex.finditer(text):
                    found.add(match.group(2).replace("\\'", "'").replace('\\"', '"'))
    found -= {"text", "error"}
    # dynamic labels: plugin names (plugin-info.json) and accent colour names
    for info in glob.glob(os.path.join(ROOT, "plugins", "*", "plugin-info.json")):
        found.add(json.load(open(info, encoding="utf-8"))["display_name"])
    sys.path.insert(0, ROOT)
    from utils.accent import ACCENT_PRESETS
    found.update(preset["label"] for preset in ACCENT_PRESETS.values())
    return sorted(found)


def main():
    strings = extract()
    catalogs = sys.argv[1:] or [os.path.basename(p)[:-5] for p in glob.glob(os.path.join(ROOT, "translations", "*.json"))]
    status = 0
    for lang in catalogs:
        path = os.path.join(ROOT, "translations", f"{lang}.json")
        catalog = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
        missing = [s for s in strings if s not in catalog]
        unused = [s for s in catalog if s not in strings]
        print(f"{lang}: {len(strings) - len(missing)}/{len(strings)} translated, {len(unused)} unused")
        for s in missing:
            print(f"  missing: {s}")
        for s in unused:
            print(f"  unused:  {s}")
        status |= bool(missing)
    if not catalogs:
        print("\n".join(strings))
    return status


if __name__ == "__main__":
    sys.exit(main())
