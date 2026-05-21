"""Pure shortcut-selection logic for the Office Hotkeys plugin.

No InkyPi render-stack imports — depends only on stdlib and the local
constants module (itself stdlib-only), so it is fast and safe to unit-test.
"""
import json
import random
import time

from . import constants


def load_shortcuts(data_path):
    """Load and return the list of shortcut dicts from a JSON file."""
    with open(data_path, encoding="utf-8") as f:
        return json.load(f)


def pick_category(categories, now=None):
    """Return the category for the current hour, rotating sequentially.

    Stateless: the index is derived from the wall clock, so the active
    category advances one step per hour with no persisted state.
    """
    if not categories:
        return None
    if now is None:
        now = time.time()
    index = int(now // 3600) % len(categories)
    return categories[index]


def filter_by_level(shortcuts, min_level):
    """Keep only shortcuts at `min_level` or harder (a difficulty floor)."""
    floor = constants.LEVELS.index(min_level)
    return [s for s in shortcuts
            if constants.LEVELS.index(s["level"]) >= floor]


def weighted_pick(items, rng):
    """Return one item, chosen with probability proportional to its `weight`."""
    if not items:
        raise ValueError("weighted_pick requires a non-empty list")
    total = sum(i["weight"] for i in items)
    threshold = rng.uniform(0, total)
    running = 0
    for item in items:
        running += item["weight"]
        if threshold <= running:
            return item
    return items[-1]


def weighted_sample(items, count, rng):
    """Return up to `count` distinct items, weighted, without replacement."""
    pool = list(items)
    chosen = []
    while pool and len(chosen) < count:
        pick = weighted_pick(pool, rng)
        chosen.append(pick)
        pool = [x for x in pool if x is not pick]
    return chosen


def _level_below(level):
    """Return the level one step easier than `level`, or None if it is the easiest."""
    index = constants.LEVELS.index(level)
    return constants.LEVELS[index - 1] if index > 0 else None


def select_for_screen(shortcuts, app, min_level, now=None, rng=None, list_size=6):
    """Pick one category (rotating, with fall-through) and build a screen.

    The pool is the category's shortcuts at `min_level` or harder. If that pool
    is too thin to fill the screen, it is topped up with shortcuts from the one
    level just below `min_level` (never further) — so an Advanced screen is
    advanced-first, filled out with intermediate shortcuts, and never shows
    beginner "noob tips". The hero is always a genuine `min_level`-or-harder
    shortcut. Returns None if the app has nothing at `min_level`.
    """
    if rng is None:
        rng = random.Random()
    if now is None:
        now = time.time()

    categories = constants.CATEGORY_ORDER[app]
    start = int(now // 3600) % len(categories)
    target = list_size + 1  # one hero + the list

    chosen_category, at_level, cat_items = None, [], []
    for offset in range(len(categories)):
        category = categories[(start + offset) % len(categories)]
        cat_items = [s for s in shortcuts
                     if s["app"] == app and s["category"] == category]
        at_level = filter_by_level(cat_items, min_level)
        if at_level:
            chosen_category = category
            break
    if chosen_category is None:
        return None

    # Top up a thin pool with the single level just below the floor.
    topped_up = []
    if len(at_level) < target:
        below = _level_below(min_level)
        if below:
            topped_up = [s for s in cat_items if s["level"] == below]
    pool = at_level + topped_up

    hero = weighted_pick(at_level, rng)
    rest = [s for s in pool if s is not hero]
    items = weighted_sample(rest, list_size, rng)

    return {
        "app": app,
        "category": chosen_category,
        "category_index": categories.index(chosen_category) + 1,
        "category_count": len(categories),
        "level": min_level,
        "hero": hero,
        "list": items,
        "pool_size": len(pool),
    }
