import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils import i18n  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_translate_and_placeholders():
    assert i18n.translate("Save", "fr") == "Enregistrer"
    assert i18n.translate("Every {n} min", "fr", n=10) == "Toutes les 10 min"
    assert i18n.translate("Every {n} min", "en", n=10) == "Every 10 min"


def test_missing_entries_and_unknown_languages_fall_back_to_english():
    assert i18n.translate("Some text that is not in the catalog", "fr") == "Some text that is not in the catalog"
    assert i18n.translate("Save", "xx") == "Save"
    assert i18n.normalize_language("xx") == "en"


def test_broken_translation_placeholder_falls_back_to_english(monkeypatch):
    monkeypatch.setitem(i18n._catalogs, "fr", {"Hello {name}": "Bonjour {nom}"})
    assert i18n.translate("Hello {name}", "fr", name="Ana") == "Hello Ana"


def test_every_marked_string_has_a_french_translation():
    result = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "extract_ui_strings.py"), "fr"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


def test_french_placeholders_match_english():
    import json
    import re
    catalog = json.load(open(os.path.join(ROOT, "src", "translations", "fr.json"), encoding="utf-8"))
    for source, translated in catalog.items():
        assert set(re.findall(r"{(\w+)}", source)) == set(re.findall(r"{(\w+)}", translated)), source
