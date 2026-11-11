import os
import stat
import sys
import threading
import time
from datetime import datetime, timedelta
from unittest import mock

import pytest
import pytz
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from model import PluginInstance, RefreshInfo  # noqa: E402
from refresh_task import RefreshTask  # noqa: E402
from utils import image_utils  # noqa: E402

TZ = pytz.timezone("Europe/Paris")


# ---------------------------------------------------------------- refresh task

class FakeConfig:
    def __init__(self, interval=600, refresh_time=None):
        self.values = {"plugin_cycle_interval_seconds": interval, "scheduler_sleep_time": 60,
                       "timezone": "Europe/Paris"}
        self.refresh_info = RefreshInfo("Playlist", None, refresh_time, None)

    def get_config(self, key, default=None):
        return self.values.get(key, default)

    def get_refresh_info(self):
        return self.refresh_info


def _task(cfg):
    return RefreshTask(cfg, display_manager=mock.Mock())


def test_wait_time_is_remaining_part_of_cycle():
    now = datetime.now(TZ)
    task = _task(FakeConfig(600, (now - timedelta(seconds=590)).isoformat()))
    assert 5 <= task._compute_wait_time() <= 11


def test_overdue_refresh_runs_immediately_after_restart():
    now = datetime.now(TZ)
    task = _task(FakeConfig(600, (now - timedelta(hours=2)).isoformat()))
    assert task._compute_wait_time() == 0
    task._first_cycle_done = True
    assert task._compute_wait_time() == 60


def test_failed_attempt_counts_as_a_cycle():
    now = datetime.now(TZ)
    task = _task(FakeConfig(600, (now - timedelta(hours=2)).isoformat()))
    task._first_cycle_done = True
    task._last_attempt_dt = now
    assert task._compute_wait_time() > 590


def test_no_previous_refresh_waits_full_cycle():
    assert _task(FakeConfig(600, None))._compute_wait_time() == 600


def test_invalid_timezone_falls_back_to_utc():
    cfg = FakeConfig()
    cfg.values["timezone"] = "Not/AZone"
    assert _task(cfg)._get_current_datetime().utcoffset() == timedelta(0)


def test_manual_update_not_lost_while_thread_busy():
    """A manual update requested while the loop is refreshing must be served right after."""
    cfg = FakeConfig(3600, datetime.now(TZ).isoformat())
    task = _task(cfg)
    calls = []

    def fake_perform(action, current_dt):
        calls.append(action)

    def slow_playlist_refresh():
        time.sleep(0.3)

    task._perform_refresh = fake_perform
    task._playlist_refresh = slow_playlist_refresh
    task._compute_wait_time = lambda: 0  # first pass: busy in a playlist refresh
    task.start()
    try:
        time.sleep(0.05)
        task._compute_wait_time = lambda: 3600
        start = time.monotonic()
        task.manual_update("action", timeout=5)
        assert calls == ["action"]
        assert time.monotonic() - start < 2
    finally:
        task.stop()


def test_manual_update_propagates_exception_and_times_out():
    cfg = FakeConfig(3600, datetime.now(TZ).isoformat())
    task = _task(cfg)

    def boom(action, current_dt):
        if action == "slow":
            time.sleep(1)
        else:
            raise ValueError("plugin failed")

    task._perform_refresh = boom
    task.start()
    try:
        with pytest.raises(ValueError):
            task.manual_update("bad", timeout=5)
        with pytest.raises(TimeoutError):
            task.manual_update("slow", timeout=0.2)
    finally:
        task.stop()


# ---------------------------------------------------------------- images

def test_change_orientation_unknown_value_does_not_crash():
    img = Image.new("RGB", (80, 48))
    assert image_utils.change_orientation(img, None).size == (80, 48)
    assert image_utils.change_orientation(img, "vertical").size == (48, 80)


def test_hung_browser_is_killed_and_temp_files_removed(tmp_path, monkeypatch):
    fake = tmp_path / "chromium"
    fake.write_text("#!/bin/sh\nsleep 30\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    monkeypatch.setattr(image_utils, "_find_chromium_binary", lambda: str(fake))
    monkeypatch.setattr(image_utils, "SCREENSHOT_PROCESS_TIMEOUT", 0.5)
    monkeypatch.setattr(image_utils.tempfile, "tempdir", str(tmp_path / "tmp"))
    os.makedirs(tmp_path / "tmp")

    start = time.monotonic()
    assert image_utils.take_screenshot_html("<html></html>", (800, 480)) is None
    assert time.monotonic() - start < 5
    assert os.listdir(tmp_path / "tmp") == []


# ---------------------------------------------------------------- scheduled refresh

def test_scheduled_refresh_not_triggered_before_scheduled_time():
    inst = PluginInstance("p", "n", {}, {"scheduled": "08:00"},
                          latest_refresh_time=TZ.localize(datetime(2026, 11, 11, 7, 10)).isoformat())
    assert not inst.should_refresh(TZ.localize(datetime(2026, 11, 11, 7, 20)))
    assert inst.should_refresh(TZ.localize(datetime(2026, 11, 11, 8, 0)))


def test_check_without_plugin_does_not_delay_next_check():
    now = datetime.now(TZ)
    cfg = FakeConfig(600, (now - timedelta(seconds=590)).isoformat())
    task = _task(cfg)
    task._determine_next_plugin = lambda *a: (None, None)  # e.g. nothing due / no active playlist
    cfg.get_playlist_manager = lambda: None
    task._playlist_refresh()
    assert task._last_attempt_dt is None
    assert task._compute_wait_time() <= 11
