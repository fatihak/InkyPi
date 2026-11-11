import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from plugins.clock.clock import Clock  # noqa: E402

TWO, THREE = [6, 8], [5, 6]


def test_word_clock_switches_to_next_hour_at_minute_33():
    at_32 = Clock.translate_word_grid_positions(2, 32)
    at_33 = Clock.translate_word_grid_positions(2, 33)
    assert TWO in at_32 and THREE not in at_32
    assert THREE in at_33 and TWO not in at_33
