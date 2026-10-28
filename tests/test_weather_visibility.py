"""Visibility values from Open-Meteo are metres in every temperature unit mode."""

import os
import sys
from datetime import datetime

import pytest
import pytz

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from plugins.weather.weather import Weather


@pytest.mark.parametrize(
    "units,metres,expected,unit",
    [
        ("imperial", 1609.344, "1.0", "mi"),
        ("imperial", 1000, "0.6", "mi"),
        ("imperial", 10000, "≥6.2", "mi"),
        ("metric", 1000, "1.0", "km"),
        ("metric", 10000, "≥10.0", "km"),
        ("standard", 1000, "1.0", "km"),
    ],
)
def test_open_meteo_visibility_metres(units, metres, expected, unit):
    # An aware time isolates conversion from separate location-time parsing behavior.
    now = datetime.now(pytz.UTC).isoformat()
    weather_data = {
        "current": {"windspeed": 0, "winddirection": 0},
        "hourly": {
            "time": [now],
            "relative_humidity_2m": [50],
            "surface_pressure": [1013],
            "visibility": [metres],
        },
    }
    air_quality = {
        "hourly": {"time": [now], "uv_index": [2], "european_aqi": [20]}
    }
    points = Weather({"id": "weather"}).parse_open_meteo_data_points(
        weather_data, air_quality, units, pytz.UTC, "24h"
    )
    visibility = next(point for point in points if point["label"] == "Visibility")
    assert visibility["measurement"] == expected
    assert visibility["unit"] == unit
