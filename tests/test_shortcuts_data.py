import json
from pathlib import Path

from src.plugins.office_hotkeys import constants

DATA = Path("src/plugins/office_hotkeys/data/shortcuts.json")
MIN_PER_CATEGORY = {"excel": 12, "outlook": 10, "powerpoint": 10}
MIN_ADVANCED = {"excel": 3, "outlook": 2, "powerpoint": 2}
MIN_ADV_PLUS_INT = {"excel": 9, "outlook": 7, "powerpoint": 7}


def load():
    return json.loads(DATA.read_text(encoding="utf-8"))


def test_dataset_is_a_nonempty_list():
    data = load()
    assert isinstance(data, list) and len(data) > 0


def test_every_entry_has_a_valid_schema():
    for s in load():
        assert set(s) == {"app", "category", "keys", "description", "level", "weight"}
        assert s["app"] in constants.CATEGORY_ORDER
        assert s["category"] in constants.CATEGORY_ORDER[s["app"]]
        assert isinstance(s["keys"], list) and s["keys"]
        assert all(isinstance(k, str) and k for k in s["keys"])
        assert isinstance(s["description"], str) and s["description"].strip()
        assert s["level"] in constants.LEVELS
        assert s["weight"] in (1, 2, 3, 4, 5)


def test_every_category_meets_its_minimum():
    data = load()
    for app, cats in constants.CATEGORY_ORDER.items():
        for cat in cats:
            n = sum(1 for s in data if s["app"] == app and s["category"] == cat)
            assert n >= MIN_PER_CATEGORY[app], f"{app}/{cat} has {n}, need {MIN_PER_CATEGORY[app]}"


def test_every_category_has_minimum_advanced():
    data = load()
    for app, cats in constants.CATEGORY_ORDER.items():
        for cat in cats:
            n = sum(1 for s in data if s["app"] == app and s["category"] == cat
                    and s["level"] == "advanced")
            assert n >= MIN_ADVANCED[app], f"{app}/{cat} has {n} advanced, need {MIN_ADVANCED[app]}"


def test_every_category_has_enough_advanced_plus_intermediate():
    data = load()
    for app, cats in constants.CATEGORY_ORDER.items():
        for cat in cats:
            n = sum(1 for s in data if s["app"] == app and s["category"] == cat
                    and s["level"] in ("advanced", "intermediate"))
            assert n >= MIN_ADV_PLUS_INT[app], \
                f"{app}/{cat} has {n} advanced+intermediate, need {MIN_ADV_PLUS_INT[app]}"
