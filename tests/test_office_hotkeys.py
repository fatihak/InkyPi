import random

from src.plugins.office_hotkeys import constants
from src.plugins.office_hotkeys import selection


def test_levels_are_ordered_easy_to_hard():
    assert constants.LEVELS == ["beginner", "intermediate", "advanced"]


def test_every_app_has_categories_and_a_theme():
    assert set(constants.CATEGORY_ORDER) == {"excel", "outlook", "powerpoint"}
    for app, cats in constants.CATEGORY_ORDER.items():
        assert len(cats) >= 4, f"{app} needs >= 4 categories"
        assert len(cats) == len(set(cats)), f"{app} has duplicate categories"
        theme = constants.APP_THEME[app]
        assert theme["label"] and theme["color"].startswith("#")


def test_excel_has_eight_categories():
    assert len(constants.CATEGORY_ORDER["excel"]) == 8


def test_pick_category_rotates_by_hour():
    cats = ["A", "B", "C"]
    assert selection.pick_category(cats, now=0) == "A"
    assert selection.pick_category(cats, now=3600) == "B"
    assert selection.pick_category(cats, now=2 * 3600) == "C"
    assert selection.pick_category(cats, now=3 * 3600) == "A"  # wraps


def test_pick_category_handles_empty_list():
    assert selection.pick_category([], now=123) is None


def test_load_shortcuts_reads_the_bundled_dataset():
    data = selection.load_shortcuts("src/plugins/office_hotkeys/data/shortcuts.json")
    assert isinstance(data, list) and len(data) > 0


def _sc(level):
    return {"app": "excel", "category": "X", "keys": ["A"],
            "description": "d", "level": level, "weight": 3}


def test_filter_by_level_is_a_floor():
    pool = [_sc("beginner"), _sc("intermediate"), _sc("advanced")]
    assert [s["level"] for s in selection.filter_by_level(pool, "beginner")] == \
        ["beginner", "intermediate", "advanced"]
    assert [s["level"] for s in selection.filter_by_level(pool, "intermediate")] == \
        ["intermediate", "advanced"]
    assert [s["level"] for s in selection.filter_by_level(pool, "advanced")] == \
        ["advanced"]


def test_filter_by_level_empty_when_nothing_qualifies():
    assert selection.filter_by_level([_sc("beginner")], "advanced") == []


def test_weighted_sample_returns_distinct_items_within_pool():
    pool = [_sc("advanced") for _ in range(5)]
    rng = random.Random(42)
    picked = selection.weighted_sample(pool, 3, rng)
    assert len(picked) == 3
    assert all(any(p is item for item in pool) for p in picked)
    assert len({id(p) for p in picked}) == 3  # distinct objects


def test_weighted_sample_caps_at_pool_size():
    pool = [_sc("advanced"), _sc("advanced")]
    assert len(selection.weighted_sample(pool, 8, random.Random(1))) == 2


def test_weighted_pick_favours_high_weight():
    heavy = {**_sc("advanced"), "weight": 5, "description": "heavy"}
    light = {**_sc("advanced"), "weight": 1, "description": "light"}
    rng = random.Random(7)
    hits = sum(1 for _ in range(400)
               if selection.weighted_pick([heavy, light], rng) is heavy)
    assert hits > 200  # heavy should dominate


def test_select_for_screen_returns_hero_and_list_from_one_category():
    data = selection.load_shortcuts("src/plugins/office_hotkeys/data/shortcuts.json")
    screen = selection.select_for_screen(data, "excel", "advanced",
                                         now=0, rng=random.Random(0))
    assert screen is not None
    assert screen["app"] == "excel"
    assert screen["category"] in constants.CATEGORY_ORDER["excel"]
    assert screen["hero"]["level"] == "advanced"
    assert all(item is not screen["hero"] for item in screen["list"])
    assert 1 <= screen["category_index"] <= screen["category_count"] == 8
    for item in screen["list"]:
        assert item["category"] == screen["category"]
        assert item["level"] in ("advanced", "intermediate")


def test_select_for_screen_falls_through_empty_categories():
    data = [{**_sc("advanced"), "category": "Pivot Tables"} for _ in range(3)]
    screen = selection.select_for_screen(data, "excel", "advanced",
                                         now=0, rng=random.Random(0))
    assert screen["category"] == "Pivot Tables"


def test_select_for_screen_tops_up_thin_pool_with_one_level_down():
    data = ([{**_sc("advanced"), "category": "Navigation"}]
            + [{**_sc("intermediate"), "category": "Navigation"} for _ in range(10)])
    screen = selection.select_for_screen(data, "excel", "advanced",
                                         now=0, rng=random.Random(0))
    levels = {screen["hero"]["level"]} | {s["level"] for s in screen["list"]}
    assert "intermediate" in levels            # thin advanced pool was topped up
    assert screen["hero"]["level"] == "advanced"   # hero is still a real advanced one


def test_select_for_screen_topup_never_reaches_beginner_at_advanced():
    data = ([{**_sc("advanced"), "category": "Navigation"}]
            + [{**_sc("intermediate"), "category": "Navigation"} for _ in range(2)]
            + [{**_sc("beginner"), "category": "Navigation"} for _ in range(10)])
    screen = selection.select_for_screen(data, "excel", "advanced",
                                         now=0, rng=random.Random(0))
    levels = {screen["hero"]["level"]} | {s["level"] for s in screen["list"]}
    assert "beginner" not in levels            # top-up stops one level down


def test_level_below():
    assert selection._level_below("advanced") == "intermediate"
    assert selection._level_below("intermediate") == "beginner"
    assert selection._level_below("beginner") is None
