import os
import sys
from datetime import datetime, timedelta
from unittest import mock

import icalendar
import pytest
import pytz

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from plugins.calendar.calendar import Calendar  # noqa: E402

TZ = pytz.timezone("Europe/Paris")



def _cal(body):
    return icalendar.Calendar.from_ical(
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//t//EN\n" + body + "END:VCALENDAR\n")


@pytest.fixture
def calendar_plugin(tmp_path, monkeypatch):
    p = Calendar({"id": "calendar"})
    monkeypatch.setattr(p, "get_plugin_dir", lambda path=None: str(tmp_path / (path or "")))
    return p


def _events(plugin, cal, start, end):
    with mock.patch.object(plugin, "fetch_calendar", return_value=cal):
        return plugin.fetch_ics_events(["u"], ["#ff0000"], TZ, start, end)


def test_event_just_after_local_midnight_is_kept(calendar_plugin):
    cal = _cal("BEGIN:VEVENT\nUID:1\nDTSTART:20261110T233000Z\nDTEND:20261110T234500Z\n"
               "SUMMARY:minuit\nEND:VEVENT\n")
    start = TZ.localize(datetime(2026, 11, 11))
    events = _events(calendar_plugin, cal, start, start + timedelta(weeks=5))
    assert [e["start"] for e in events] == ["2026-11-11T00:30:00+01:00"]


def test_floating_times_use_configured_timezone(calendar_plugin, monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    cal = _cal("BEGIN:VEVENT\nUID:1\nDTSTART:20261112T090000\nDTEND:20261112T100000\n"
               "SUMMARY:cours\nEND:VEVENT\n")
    start = TZ.localize(datetime(2026, 11, 11))
    events = _events(calendar_plugin, cal, start, start + timedelta(weeks=1))
    assert events[0]["start"] == "2026-11-12T09:00:00+01:00"
    assert events[0]["end"] == "2026-11-12T10:00:00+01:00"


def test_date_value_with_tzid_stays_all_day(calendar_plugin):
    cal = _cal("BEGIN:VEVENT\nUID:1\nDTSTART;TZID=Europe/Paris;VALUE=DATE:20261114\n"
               "DTEND;TZID=Europe/Paris;VALUE=DATE:20261115\nSUMMARY:conge\nEND:VEVENT\n"
               "BEGIN:VEVENT\nUID:2\nDTSTART;VALUE=DATE:20261116\nRRULE:FREQ=DAILY;COUNT=2\n"
               "SUMMARY:recurrent\nEND:VEVENT\n")
    start = TZ.localize(datetime(2026, 11, 11))
    cal = Calendar._normalize_date_values(cal)
    events = sorted(_events(calendar_plugin, cal, start, start + timedelta(weeks=2)), key=lambda e: e["start"])
    assert [(e["title"], e["start"], e["allDay"]) for e in events] == [
        ("conge", "2026-11-14", True), ("recurrent", "2026-11-16", True), ("recurrent", "2026-11-17", True)]
    assert events[0]["end"] == "2026-11-15"
