import os
import sys
from datetime import datetime
from unittest import mock

import pytest
import pytz
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from plugins.calendar import calendar as calendar_module  # noqa: E402
from plugins.calendar.calendar import Calendar  # noqa: E402

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:1
DTSTART:20261112T090000Z
DTEND:20261112T100000Z
SUMMARY:Cours
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART:20261113T090000Z
DURATION:PT2H
SUMMARY:TP
END:VEVENT
END:VCALENDAR
"""

GOOD = "https://good.example/cal.ics?token=SECRET"
BAD = "https://bad.example/cal.ics?token=SECRET"


def _resp(text, status=200):
    r = mock.Mock()
    r.text = text
    r.status_code = status
    r.iter_content = lambda chunk_size=None: [text.encode()]
    r.close = mock.Mock()
    r.raise_for_status = mock.Mock()
    return r


def _fake_get(url, timeout=None, **kwargs):
    if url.startswith("https://bad."):
        raise requests.exceptions.ConnectTimeout("timed out")
    return _resp(ICS)


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    monkeypatch.setattr(calendar_module, "RETRY_BACKOFF_SECONDS", 0)
    p = Calendar({"id": "calendar"})
    monkeypatch.setattr(p, "get_plugin_dir", lambda path=None: str(tmp_path / (path or "")))
    return p


RANGE = (datetime(2026, 11, 11), datetime(2026, 12, 1))
TZ = pytz.timezone("Europe/Paris")


def test_one_failing_calendar_does_not_break_others(plugin):
    with mock.patch.object(calendar_module.requests, "get", side_effect=_fake_get) as get:
        events = plugin.fetch_ics_events([GOOD, BAD], ["#ff0000", "#00ff00"], TZ, *RANGE)
    assert {e["title"] for e in events} == {"Cours", "TP"}
    assert all(e["backgroundColor"] == "#ff0000" for e in events)
    # bad url retried FETCH_ATTEMPTS times
    assert sum(1 for c in get.call_args_list if c.args[0] == BAD) == calendar_module.FETCH_ATTEMPTS


def test_all_failing_raises(plugin):
    with mock.patch.object(calendar_module.requests, "get", side_effect=_fake_get):
        with pytest.raises(RuntimeError) as exc:
            plugin.fetch_ics_events([BAD], ["#ff0000"], TZ, *RANGE)
    assert "SECRET" not in str(exc.value)


def test_falls_back_to_cache(plugin):
    with mock.patch.object(calendar_module.requests, "get", return_value=_resp(ICS)):
        plugin.fetch_calendar(GOOD)
    with mock.patch.object(calendar_module.requests, "get",
                           side_effect=requests.exceptions.ConnectionError("down")):
        events = plugin.fetch_ics_events([GOOD], ["#ff0000"], TZ, *RANGE)
    assert len(events) == 2


def test_duration_end_is_converted_to_timezone(plugin):
    with mock.patch.object(calendar_module.requests, "get", return_value=_resp(ICS)):
        events = plugin.fetch_ics_events([GOOD], ["#ff0000"], TZ, *RANGE)
    tp = next(e for e in events if e["title"] == "TP")
    assert tp["start"] == "2026-11-13T10:00:00+01:00"
    assert tp["end"] == "2026-11-13T12:00:00+01:00"


def test_errors_and_logs_never_contain_the_private_url(plugin, caplog):
    err = requests.exceptions.HTTPError("404 Client Error for url: " + BAD)
    err.response = mock.Mock(status_code=404)
    with mock.patch.object(calendar_module.requests, "get", side_effect=err):
        with pytest.raises(RuntimeError) as exc:
            plugin.fetch_ics_events([BAD], ["#ff0000"], TZ, *RANGE)
    assert "SECRET" not in str(exc.value) and "HTTP 404" in str(exc.value)
    assert "SECRET" not in caplog.text


def test_redact_hides_credentials():
    assert Calendar._redact("https://user:pa55@host.example:8443/cal.ics?token=x") == "https://host.example:8443/..."


def test_slow_download_is_cut_by_the_deadline(plugin, monkeypatch):
    clock = iter(range(0, 100000, 30))  # every clock reading advances 30 s
    slow = _resp(ICS)
    slow.iter_content = lambda chunk_size=None: iter([b"x"] * 100)
    with mock.patch("time.monotonic", side_effect=lambda: next(clock)), \
         mock.patch.object(calendar_module.requests, "get", return_value=slow):
        with pytest.raises(RuntimeError):
            plugin.fetch_calendar(GOOD)
