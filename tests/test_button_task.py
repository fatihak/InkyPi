import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from button_task import ButtonTask


class FakeConfig:
    def __init__(self, values):
        self.values = values

    def get_config(self, key=None, default={}):
        if key is None:
            return self.values
        return self.values.get(key, default)


class FakeRefreshTask:
    def __init__(self):
        self.cycle_count = 0

    def cycle_playlist_next(self):
        self.cycle_count += 1


class FakeEvent:
    def __init__(self, line_offset):
        self.line_offset = line_offset


def test_button_task_is_enabled_only_for_inky_display():
    refresh_task = FakeRefreshTask()

    assert ButtonTask(FakeConfig({"display_type": "inky"}), refresh_task).is_enabled()
    assert not ButtonTask(FakeConfig({"display_type": "mock"}), refresh_task).is_enabled()


def test_button_a_press_cycles_playlist_and_debounces(monkeypatch):
    refresh_task = FakeRefreshTask()
    button_task = ButtonTask(
        FakeConfig({
            "display_type": "inky",
            "button_debounce_seconds": 1.0,
        }),
        refresh_task,
    )
    button_task.offsets = [7]

    times = iter([10.0, 10.5, 11.1])
    monkeypatch.setattr("button_task.time.monotonic", lambda: next(times))

    button_task._handle_button_event(FakeEvent(7))
    button_task._handle_button_event(FakeEvent(7))
    button_task._handle_button_event(FakeEvent(7))

    assert refresh_task.cycle_count == 2


def test_button_task_ignores_other_lines():
    refresh_task = FakeRefreshTask()
    button_task = ButtonTask(FakeConfig({"display_type": "inky"}), refresh_task)
    button_task.offsets = [7]

    button_task._handle_button_event(FakeEvent(8))

    assert refresh_task.cycle_count == 0
