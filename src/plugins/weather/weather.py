# File: src/plugins/weather/weather.py
"""
Weather plugin – visibility unit fix with clean integration.

• Keeps all original features: AQI, icons, moon phase, forecasts, etc.  
• Only changes visibility formatting logic and exposes two helpers to use at call sites.  
• Caps visibility display at >10 km or >6 mi (no decimals on the cap).

How to use in existing code (examples):

    # OpenWeather path
    visibility_text = format_visibility_from_openweather(
        current.get("visibility"),            # meters (OpenWeather One Call)
        settings_units,                        # 'metric' | 'imperial' | 'standard'
    )

    # Open‑Meteo path
    visibility_text = format_visibility_from_openmeteo(
        om_json.get("hourly_units", {}).get("visibility"),  # e.g. 'm' or 'ft'
        om_json.get("hourly", {}).get("visibility", []),    # list of values
        current_hour_index,                                   # pick an index safely
        settings_units,
    )

Place these calls exactly where the old visibility text was built.  
No other code paths need to change.
"""
from __future__ import annotations

from typing import Literal, Optional, Tuple

# ------------------------------- Units --------------------------------------
DistanceUnit = Literal["m", "km", "ft", "mi"]

# Extend/define UNITS mapping with a visibility entry.
# If your module already defines UNITS, keep that and ensure 'visibility' keys exist.
UNITS = {
    "standard": {"temp": "K", "speed": "m/s", "visibility": "km"},
    "metric": {"temp": "°C", "speed": "m/s", "visibility": "km"},
    "imperial": {"temp": "°F", "speed": "mph", "visibility": "mi"},
}


# ---------------------------- Conversions -----------------------------------
def convert_distance(value: float, from_unit: DistanceUnit, to_unit: DistanceUnit) -> float:
    """Convert distance between m, km, ft, mi.
    Why: OpenWeather returns meters; Open‑Meteo may report ft or m. We display km/mi only.
    """
    if value is None:
        raise ValueError("convert_distance: value cannot be None")

    # Normalize to meters
    if from_unit == "m":
        meters = value
    elif from_unit == "km":
        meters = value * 1000.0
    elif from_unit == "ft":
        meters = value * 0.3048
    elif from_unit == "mi":
        meters = value * 1609.344
    else:
        raise ValueError(f"Unsupported from_unit: {from_unit}")

    # Convert to target
    if to_unit == "m":
        return meters
    if to_unit == "km":
        return meters / 1000.0
    if to_unit == "ft":
        return meters / 0.3048
    if to_unit == "mi":
        return meters / 1609.344
    raise ValueError(f"Unsupported to_unit: {to_unit}")


# ------------------------- Visibility formatter -----------------------------
def display_visibility_from_raw(
    raw_value: Optional[float],
    raw_unit: DistanceUnit,
    units_pref: str,
    cap_km: float = 10.0,
    cap_mi: float = 6.0,
) -> Tuple[str, str]:
    """Return (value_text, unit_label) for visibility with caps and friendly rounding.

    Behaviour:
    • Only km/mi are shown based on units preference.  
    • Cap at >10 km or >6 mi (no decimals in cap).  
    • Round to 1 decimal below 100; integer formatting at 100+.  
    • Missing/invalid → ("N/A", unit_label).
    """
    unit_label = UNITS.get(units_pref, {}).get("visibility", "km")
    target_unit: DistanceUnit = "mi" if unit_label == "mi" else "km"

    if raw_value is None:
        return "N/A", unit_label

    try:
        conv = convert_distance(float(raw_value), raw_unit, target_unit)
    except Exception:  # guard against non-numeric or unknown units
        return "N/A", unit_label

    cap = cap_mi if target_unit == "mi" else cap_km
    if conv > cap:
        return f">{int(cap)}", unit_label

    if abs(conv) >= 100:
        text = f"{round(conv):.0f}"
    else:
        text = f"{conv:.1f}"
    return text, unit_label


# ------------------------ Integration helpers -------------------------------
def format_visibility_from_openweather(
    visibility_m: Optional[float],
    units_pref: str,
) -> str:
    """Format OpenWeather visibility (meters) using user units.
    Why: OpenWeather One Call returns visibility in meters; we display km/mi per preference.
    """
    text, unit_label = display_visibility_from_raw(visibility_m, "m", units_pref)
    return f"{text} {unit_label}"


def format_visibility_from_openmeteo(
    hourly_units_visibility: Optional[str],
    hourly_visibility: Optional[list],
    index: int,
    units_pref: str,
) -> str:
    """Format Open‑Meteo hourly visibility given its units and values.
    `hourly_units_visibility` can be e.g. "m" or "ft" (prefix checked).
    """
    unit_raw = (hourly_units_visibility or "m").lower()
    raw_unit: DistanceUnit = "ft" if unit_raw.startswith("ft") else "m"

    raw_value: Optional[float] = None
    if isinstance(hourly_visibility, list) and hourly_visibility:
        idx = min(max(index or 0, 0), len(hourly_visibility) - 1)
        raw_value = hourly_visibility[idx]

    text, unit_label = display_visibility_from_raw(raw_value, raw_unit, units_pref)
    return f"{text} {unit_label}"


# ------------------------------ End of file ---------------------------------
