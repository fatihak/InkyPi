# src/plugins/weather/weather.py

from plugins.base_plugin.base_plugin import BasePlugin
import logging
import math
import os
from datetime import datetime
from io import BytesIO
from typing import Optional, Tuple, Dict, Any, List

import pytz
import requests
from PIL import Image

logger = logging.getLogger(__name__)

# -----------------------------
# Configuration / Constants
# -----------------------------
UNITS = {
    "standard": {"temperature": "K",  "speed": "m/s", "visibility": "km"},
    "metric":   {"temperature": "°C", "speed": "m/s", "visibility": "km"},
    "imperial": {"temperature": "°F", "speed": "mph", "visibility": "mi"},
}

# OpenWeather (One Call 3.0)
WEATHER_URL = "https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&units={units}&exclude=minutely&appid={api_key}"
AIR_QUALITY_URL = "http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={api_key}"
GEOCODING_URL = "http://api.openweathermap.org/geo/1.0/reverse?lat={lat}&lon={long}&limit=1&appid={api_key}"

# Open-Meteo (example; adjust params to your taste)
OPEN_METEO_FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&hourly=visibility"
    "&timezone={tz}"
)

_M_PER_KM = 1000.0
_M_PER_MI = 1609.344
_FT_PER_MI = 5280.0
_M_PER_FT = 0.3048

# -----------------------------
# Distance / display helpers
# -----------------------------
def convert_distance(value: Optional[float], from_unit: str, to_unit: str) -> Optional[float]:
    """
    Convert a distance between m, km, and mi.
    from_unit/to_unit ∈ {'m','km','mi'}.
    """
    if value is None:
        return None
    v = float(value)

    # to meters
    if from_unit == "m":
        meters = v
    elif from_unit == "km":
        meters = v * _M_PER_KM
    elif from_unit == "mi":
        meters = v * _M_PER_MI
    elif from_unit == "ft":
        meters = v * _M_PER_FT
    else:
        # default: assume meters
        meters = v

    # to target
    if to_unit == "m":
        return meters
    if to_unit == "km":
        return meters / _M_PER_KM
    if to_unit == "mi":
        return meters / _M_PER_MI
    raise ValueError(f"Unsupported to_unit: {to_unit}")

def display_visibility_from_raw(
    raw_value: Optional[float],
    *,
    raw_unit: str,          # 'm' or 'ft' typically (Open-Meteo); 'm' for OpenWeather
    units_pref: str,        # 'metric' | 'imperial' | 'standard'
    decimals: int = 1,
) -> Tuple[str, str]:
    """
    Returns (display_value_str, display_unit_str) for visibility.

    - Converts raw value from raw_unit into km (metric/standard) or mi (imperial)
    - Applies common report caps: >10.0 km or >6.2 mi
    - Rounds neatly
    - If raw_value is None, returns ("N/A", target_unit)
    """
    target_unit = UNITS.get(units_pref, {}).get("visibility", "km")  # 'km' or 'mi'
    if raw_value is None:
        return "N/A", target_unit

    # Normalize 'raw_unit' for safety
    ru = raw_unit.lower()
    if ru not in ("m", "km", "mi", "ft"):
        # default to meters if unknown
        ru = "m"

    converted = convert_distance(raw_value, from_unit=ru, to_unit=target_unit)
    if converted is None:
        return "N/A", target_unit

    # Cap thresholds
    KM_CAP = 10.0
    MI_CAP = KM_CAP / 1.609344  # ≈ 6.2137

    if target_unit == "mi":
        if converted >= MI_CAP:
            return ">6.2", "mi"
    else:
        if converted >= KM_CAP:
            return ">10.0", "km"

    # Nice rounding
    if converted >= 100:
        disp = f"{round(converted, 0):.0f}"
    else:
        disp = f"{round(converted, decimals):.{decimals}f}"
    return disp, target_unit

# -----------------------------
# Weather Plugin
# -----------------------------
class Weather(BasePlugin):
    """
    Minimal, self-contained plugin file that demonstrates updated visibility handling
    for both Open-Meteo and OpenWeather without altering your broader UI.

    Integrate as needed with your existing rendering / data pipeline.
    """

    plugin_name = "Weather"
    description = "Weather plugin with consistent visibility display in km/mi."

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    # ---------- Fetchers (optional; keep if you fetch here) ----------
    def fetch_openweather(self, lat: float, lon: float, units: str, api_key: str) -> Dict[str, Any]:
        url = WEATHER_URL.format(lat=lat, lon=lon, units=units, api_key=api_key)
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.json()

    def fetch_openmeteo(self, lat: float, lon: float, tz_str: str = "auto") -> Dict[str, Any]:
        # Open-Meteo will accept a timezone string like "America/New_York" or "auto"
        url = OPEN_METEO_FORECAST_URL.format(lat=lat, lon=lon, tz=tz_str)
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        return r.json()

    # ---------- Paths ----------
    def get_plugin_dir(self, relative: str) -> str:
        """Resolve resource path (icons, etc.)."""
        base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, relative)

    # ---------- Render helpers ----------
    def _get_tz(self, tz_name: Optional[str]) -> pytz.BaseTzInfo:
        try:
            if tz_name:
                return pytz.timezone(tz_name)
        except Exception:
            pass
        return pytz.utc

    # ---------- Visibility (OpenWeather) ----------
    def build_visibility_from_openweather(
        self,
        weather_data: Dict[str, Any],
        units: str,
        tz_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        OpenWeather OneCall: visibility is in meters under `current.visibility`.
        Convert to km/mi for display with caps.
        """
        unit_label = "mi" if units == "imperial" else "km"
        measurement = "N/A"

        current = (weather_data or {}).get("current", {})
        vis_m = current.get("visibility")  # meters

        # Convert m -> km/mi
        value_str, _ = display_visibility_from_raw(vis_m, raw_unit="m", units_pref=units)
        measurement = value_str

        return {
            "label": "Visibility",
            "measurement": measurement,
            "unit": unit_label,
            "icon": self.get_plugin_dir("icons/visibility.png"),
        }

    # ---------- Visibility (Open-Meteo) ----------
    def build_visibility_from_openmeteo(
        self,
        weather_data: Dict[str, Any],
        units: str,
    ) -> Dict[str, Any]:
        """
        Open-Meteo hourly visibility, with reported units in `hourly_units.visibility`
        ('m' or 'ft' typically). We display as km (metric/standard) or mi (imperial).
        """
        hourly = (weather_data or {}).get("hourly", {}) or {}
        hourly_units = (weather_data or {}).get("hourly_units", {}) or {}

        tz_name = (weather_data or {}).get("timezone") or "UTC"
        tz = self._get_tz(tz_name)
        now_local = datetime.now(tz)

        times: List[str] = hourly.get("time", []) or []
        vis_values: List[Optional[float]] = hourly.get("visibility", []) or []
        vis_unit_reported: str = (hourly_units.get("visibility") or "m").lower()

        # Find the entry matching the current local hour
        idx_match = None
        for i, t in enumerate(times):
            try:
                dt_local = datetime.fromisoformat(t).astimezone(tz)
            except ValueError:
                logger.warning("Could not parse time string %s for visibility.", t)
                continue
            if dt_local.hour == now_local.hour and i < len(vis_values):
                idx_match = i
                break

        # Fallback to the first value if no exact hour match
        if idx_match is None and vis_values:
            idx_match = 0

        unit_label = "mi" if units == "imperial" else "km"
        if idx_match is None:
            value_str = "N/A"
        else:
            raw_val = vis_values[idx_match]
            value_str, _ = display_visibility_from_raw(
                raw_val, raw_unit=vis_unit_reported, units_pref=units
            )

        return {
            "label": "Visibility",
            "measurement": value_str,
            "unit": unit_label,
            "icon": self.get_plugin_dir("icons/visibility.png"),
        }

    # ---------- Example render that builds a simple card ----------
    def render_weather_card_from_openmeteo(
        self, weather_data: Dict[str, Any], units: str = "metric"
    ) -> Dict[str, Any]:
        """
        Example renderer that returns a minimal set of datapoints from an Open-Meteo response.
        Extend as needed for temp, wind, etc.
        """
        data_points = []
        data_points.append(self.build_visibility_from_openmeteo(weather_data, units))
        return {"source": "open-meteo", "data_points": data_points}

    def render_weather_card_from_openweather(
        self, weather_data: Dict[str, Any], units: str = "metric"
    ) -> Dict[str, Any]:
        """
        Example renderer that returns a minimal set of datapoints from an OpenWeather response.
        Extend as needed for temp, wind, etc.
        """
        data_points = []
        data_points.append(self.build_visibility_from_openweather(weather_data, units))
        return {"source": "openweather", "data_points": data_points}
