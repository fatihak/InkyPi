import os
import sys
from datetime import datetime, timedelta
from unittest import mock

import pytest
import pytz
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from plugins.weather import weather as weather_module  # noqa: E402
from plugins.weather.weather import Weather  # noqa: E402

TZ = pytz.timezone("Europe/Paris")

@pytest.fixture
def weather_plugin(tmp_path, monkeypatch):
    monkeypatch.setattr(weather_module, "RETRY_BACKOFF_SECONDS", 0)
    p = Weather({"id": "weather"})
    monkeypatch.setattr(p, "get_plugin_dir", lambda path=None: str(tmp_path / (path or "")))
    return p


def _resp(status=200, payload=None, text=""):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = payload
    r.text = text
    r.iter_content = lambda chunk_size=None: [b"{}"]
    r.close = mock.Mock()
    return r


def test_fetch_retries_then_succeeds(weather_plugin):
    responses = [_resp(429, text='{"reason":"The service is overloaded"}'), _resp(200, {"ok": 1})]
    with mock.patch.object(weather_module.requests, "get", side_effect=responses) as get:
        assert weather_plugin._fetch_json("https://api/x", "test") == {"ok": 1}
    assert get.call_count == 2


def test_fetch_falls_back_to_cache(weather_plugin):
    with mock.patch.object(weather_module.requests, "get", return_value=_resp(200, {"v": 42})):
        weather_plugin._fetch_json("https://api/x", "test")
    with mock.patch.object(weather_module.requests, "get",
                           side_effect=requests.exceptions.ReadTimeout("timeout")):
        assert weather_plugin._fetch_json("https://api/x", "test") == {"v": 42}


def test_fetch_without_cache_raises(weather_plugin):
    with mock.patch.object(weather_module.requests, "get",
                           side_effect=requests.exceptions.ConnectionError("down")):
        with pytest.raises(RuntimeError):
            weather_plugin._fetch_json("https://api/never", "test")


def test_optional_fetch_returns_empty_on_error(weather_plugin):
    def boom(*a):
        raise RuntimeError("aqi down")
    assert weather_plugin._optional(boom, 1, 2) == {}


def test_open_meteo_times_are_read_in_configured_timezone(weather_plugin, monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    dt = weather_plugin._parse_local("2026-11-11T07:53", TZ)
    assert dt.hour == 7 and dt.utcoffset() == timedelta(hours=1)


def _hourly(now, **series):
    base = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    times = [(base + timedelta(hours=h)).isoformat(timespec="minutes") for h in range(24)]
    return {"time": times, **series}


def test_data_points_tolerate_missing_and_null_values(weather_plugin):
    now = datetime.now(TZ)
    weather_data = {
        "daily": {"sunrise": [], "sunset": []},
        "current": {"windspeed": 3, "winddirection": 90},
        "hourly": _hourly(now, relative_humidity_2m=[None] * 24, surface_pressure=[1013.6] * 24),
    }
    points = weather_plugin.parse_open_meteo_data_points(weather_data, {}, "metric", TZ, "24h")
    by_label = {p["label"]: p["measurement"] for p in points}
    assert by_label["Humidity"] == "N/A"
    assert by_label["Pressure"] == 1014
    assert by_label["Visibility"] == "N/A"
    assert by_label["UV Index"] == "N/A"
    assert by_label["Air Quality"] == "N/A"


def test_forecast_high_low_are_rounded(weather_plugin):
    daily = {"time": ["2026-11-11"], "weathercode": [1],
             "temperature_2m_max": [12.9], "temperature_2m_min": [4.5]}
    forecast = weather_plugin.parse_open_meteo_forecast(daily, "metric", TZ, 1, 44.0)
    assert forecast[0]["high"] == 13


def test_weather_errors_do_not_leak_api_key(weather_plugin, caplog):
    url = "https://api.openweathermap.org/data/3.0/onecall?appid=SECRETKEY"
    with mock.patch.object(weather_module.requests, "get",
                           side_effect=requests.exceptions.ConnectionError(f"Max retries exceeded with url: {url}")):
        with pytest.raises(RuntimeError) as exc:
            weather_plugin._fetch_json(url, "test")
    assert "SECRETKEY" not in str(exc.value) and "SECRETKEY" not in caplog.text


def test_open_meteo_timezone_is_url_encoded(weather_plugin):
    with mock.patch.object(weather_plugin, "_fetch_json", return_value={}) as fetch:
        weather_plugin.get_open_meteo_data(1, 2, "metric", 3, pytz.timezone("Etc/GMT+5"))
    assert "timezone=Etc/GMT%2B5" in fetch.call_args.args[0]


def test_location_is_cached_for_outages(weather_plugin):
    with mock.patch.object(weather_plugin, "_fetch_json", return_value=[{"name": "Talence", "country": "FR"}]) as fetch:
        assert weather_plugin.get_location("KEY", 1, 2) == "Talence, FR"
    assert fetch.call_args.args[1] == "location"
