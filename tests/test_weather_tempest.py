import os
import sys
import types
from unittest.mock import Mock, patch

import pytest
import pytz


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Keep this focused test runnable on a minimal host that has not activated the
# project's development environment. Production installs include astral.
try:
    import astral  # noqa: F401
except ModuleNotFoundError:
    astral_stub = types.ModuleType("astral")
    astral_stub.moon = types.SimpleNamespace(phase=lambda _date: 0.0)
    sys.modules["astral"] = astral_stub

from plugins.weather.weather import Weather


def make_weather():
    return Weather({"id": "weather"})


def sample_tempest_response():
    return {
        "station_id": 12345,
        "station_name": "Backyard Tempest",
        "timezone": "America/New_York",
        "obs": [
            {
                "timestamp": 1789142400,
                "air_temperature": 20.0,
                "relative_humidity": 61,
                "wind_avg": 5.0,
                "wind_direction": 90,
                "sea_level_pressure": 1012.6,
                "uv": 3.2,
                "precip_accum_local_day": 25.4,
                "strike_count": 2,
            }
        ],
    }


def sample_open_meteo_response():
    return {
        "current": {
            "time": "2026-09-11T12:00:00+00:00",
            "temperature": 19.0,
            "windspeed": 1.0,
            "winddirection": 180,
            "is_day": 1,
            "precipitation": 0,
            "weather_code": 1,
            "apparent_temperature": 19.0,
        },
        "daily": {
            "time": ["2026-09-11", "2026-09-12"],
            "weathercode": [1, 2],
            "temperature_2m_max": [22, 23],
            "temperature_2m_min": [12, 13],
            "sunrise": ["2026-09-11T06:30:00+00:00", "2026-09-12T06:31:00+00:00"],
            "sunset": ["2026-09-11T19:00:00+00:00", "2026-09-12T18:58:00+00:00"],
        },
        "hourly": {
            "time": ["2026-09-11T12:00:00+00:00"],
            "temperature_2m": [19.0],
            "precipitation": [0.0],
            "precipitation_probability": [10],
            "relative_humidity_2m": [50],
            "surface_pressure": [1000],
            "visibility": [10000],
            "weather_code": [1],
        },
    }


def sample_air_quality_response():
    return {
        "hourly": {
            "time": ["2026-09-11T12:00:00+00:00"],
            "european_aqi": [20],
            "uv_index": [2.0],
        }
    }


class FakeDeviceConfig:
    def load_env_key(self, key):
        return "fresh-test-token" if key == "TEMPEST_TOKEN" else None

    def get_config(self, key, default=None):
        return {
            "timezone": "UTC",
            "time_format": "24h",
            "orientation": "horizontal",
        }.get(key, default)

    def get_resolution(self):
        return (800, 480)


def test_get_tempest_data_uses_token_as_query_param_without_embedding_it_in_url():
    weather = make_weather()
    response = Mock(status_code=200)
    response.json.return_value = sample_tempest_response()

    with patch("plugins.weather.weather.requests.get", return_value=response) as get:
        result = weather.get_tempest_data("fresh-test-token", "12345")

    assert result["station_id"] == 12345
    get.assert_called_once_with(
        "https://swd.weatherflow.com/swd/rest/observations/station/12345",
        params={"token": "fresh-test-token"},
        timeout=30,
    )
    assert "fresh-test-token" not in get.call_args.args[0]


def test_get_tempest_data_rejects_http_error():
    weather = make_weather()
    response = Mock(status_code=401)

    with patch("plugins.weather.weather.requests.get", return_value=response):
        with pytest.raises(RuntimeError, match="Failed to retrieve Tempest station observation"):
            weather.get_tempest_data("bad-token", "12345")


@pytest.mark.parametrize(
    "units,expected_temp,expected_wind,expected_rain",
    [
        ("metric", 20.0, 5.0, 25.4),
        ("imperial", 68.0, 11.184681460272, 1.0),
        ("standard", 293.15, 5.0, 25.4),
    ],
)
def test_tempest_unit_conversions(units, expected_temp, expected_wind, expected_rain):
    weather = make_weather()
    assert weather.convert_tempest_temperature(20, units) == pytest.approx(expected_temp)
    assert weather.convert_tempest_wind_speed(5, units) == pytest.approx(expected_wind)
    assert weather.convert_tempest_precipitation(25.4, units) == pytest.approx(expected_rain)


def test_parse_tempest_data_uses_station_observation_for_current_values(monkeypatch):
    weather = make_weather()
    tz = pytz.UTC
    forecast = sample_open_meteo_response()
    aqi = sample_air_quality_response()

    monkeypatch.setattr(
        weather,
        "parse_open_meteo_forecast",
        lambda *args, **kwargs: [{"day": "Thu", "high": 22, "low": 12, "icon": "icon", "moon_phase_pct": "50", "moon_phase_icon": "moon"}],
    )
    monkeypatch.setattr(
        weather,
        "parse_open_meteo_hourly",
        lambda *args, **kwargs: [{"time": "12 PM", "temperature": 19, "precipitation": 0.1, "rain": 0, "icon": "icon"}],
    )
    monkeypatch.setattr(
        weather,
        "parse_open_meteo_data_points",
        lambda *args, **kwargs: [
            {"label": "Sunrise", "measurement": "6:30", "unit": "AM", "icon": "sunrise"},
            {"label": "Sunset", "measurement": "7:00", "unit": "PM", "icon": "sunset"},
            {"label": "Wind", "measurement": 1, "unit": "m/s", "icon": "wind", "arrow": "↑"},
            {"label": "Humidity", "measurement": 50, "unit": "%", "icon": "humidity"},
            {"label": "Pressure", "measurement": 1000, "unit": "hPa", "icon": "pressure"},
            {"label": "UV Index", "measurement": 2, "unit": "", "icon": "uv"},
            {"label": "Visibility", "measurement": "10", "unit": "km", "icon": "visibility"},
            {"label": "Air Quality", "measurement": 20, "unit": "Fair", "icon": "aqi"},
        ],
    )

    data = weather.parse_tempest_data(
        sample_tempest_response(), forecast, aqi, tz, "imperial", "12h", 40.0
    )

    assert data["current_temperature"] == "68"
    assert data["feels_like"] == "68"
    assert data["temperature_unit"] == "°F"

    metrics = {item["label"]: item for item in data["data_points"]}
    assert metrics["Wind"]["measurement"] == pytest.approx(11.2)
    assert metrics["Humidity"]["measurement"] == 61
    assert metrics["Pressure"]["measurement"] == pytest.approx(1012.6)
    assert metrics["UV Index"]["measurement"] == pytest.approx(3.2)
    assert metrics["Rain Today"]["measurement"] == pytest.approx(1.0)
    assert metrics["Rain Today"]["unit"] == "in"
    assert metrics["Lightning"]["measurement"] == 2


def test_parse_tempest_data_requires_current_observation():
    weather = make_weather()
    with pytest.raises(RuntimeError, match="current station observation"):
        weather.parse_tempest_data(
            {"obs": []}, {}, {}, pytz.UTC, "metric", "24h", 0.0
        )


def test_generate_image_tempest_dispatches_station_current_and_open_meteo_forecast(monkeypatch):
    weather = make_weather()
    tempest = sample_tempest_response()
    forecast = sample_open_meteo_response()
    aqi = sample_air_quality_response()

    get_tempest = Mock(return_value=tempest)
    get_forecast = Mock(return_value=forecast)
    get_aqi = Mock(return_value=aqi)
    parse_tempest = Mock(return_value={"title": "placeholder"})
    render = Mock(return_value="rendered-image")

    monkeypatch.setattr(weather, "get_tempest_data", get_tempest)
    monkeypatch.setattr(weather, "get_open_meteo_data", get_forecast)
    monkeypatch.setattr(weather, "get_open_meteo_air_quality", get_aqi)
    monkeypatch.setattr(weather, "parse_tempest_data", parse_tempest)
    monkeypatch.setattr(weather, "render_image", render)

    settings = {
        "latitude": "40.0",
        "longitude": "-75.0",
        "units": "metric",
        "weatherProvider": "Tempest",
        "tempestStationId": "12345",
        "titleSelection": "location",
        "weatherTimeZone": "locationTimeZone",
    }

    result = weather.generate_image(settings, FakeDeviceConfig())

    assert result == "rendered-image"
    get_tempest.assert_called_once_with("fresh-test-token", "12345")
    get_forecast.assert_called_once_with(40.0, -75.0, "metric", 8)
    get_aqi.assert_called_once_with(40.0, -75.0)
    parse_tempest.assert_called_once()
    assert parse_tempest.call_args.args[0] is tempest
    assert parse_tempest.call_args.args[1] is forecast
    assert parse_tempest.call_args.args[2] is aqi
    assert parse_tempest.call_args.args[3].zone == "America/New_York"
    assert parse_tempest.call_args.args[4:] == ("metric", "24h", 40.0)

    render.assert_called_once()
    render_params = render.call_args.args[3]
    assert render_params["title"] == "Backyard Tempest"
    assert render_params["plugin_settings"]["tempestStationId"] == "12345"
    assert "token" not in " ".join(render_params["plugin_settings"].keys()).lower()
