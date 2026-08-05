"""Fetches and normalizes Open-Meteo weather data into typed snapshots ready
for pi_weather_display.canvas to draw. Ported from src/plugins/weather/weather.py
(Open-Meteo path only - no OpenWeatherMap, no other plugin machinery)."""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, date

import pytz
import requests
from astral import moon

from config import DisplayConfig

logger = logging.getLogger(__name__)

DUTCH_WEEKDAYS = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
DUTCH_WEEKDAYS_ABBR = ["ma", "di", "wo", "do", "vr", "za", "zo"]
DUTCH_MONTHS = [
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december"
]

UNITS = {
    "standard": {"temperature": "K", "speed": "m/s", "distance": "km"},
    "metric": {"temperature": "°C", "speed": "m/s", "distance": "km"},
    "imperial": {"temperature": "°F", "speed": "mph", "distance": "mi"},
}

NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={long}&format=jsonv2&accept-language=nl&zoom=14"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={long}&hourly=weather_code,temperature_2m,precipitation,precipitation_probability,relative_humidity_2m,surface_pressure,visibility&daily=weathercode,temperature_2m_max,temperature_2m_min,sunrise,sunset&current=temperature,windspeed,winddirection,is_day,precipitation,weather_code,apparent_temperature&timezone=auto&models=best_match&forecast_days={forecast_days}"
OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={long}&hourly=european_aqi,uv_index,uv_index_clear_sky&timezone=auto"
OPEN_METEO_UNIT_PARAMS = {
    "standard": "temperature_unit=celsius&wind_speed_unit=ms&precipitation_unit=mm",
    "metric": "temperature_unit=celsius&wind_speed_unit=ms&precipitation_unit=mm",
    "imperial": "temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch",
}


def format_date_nl(dt: datetime) -> str:
    date_str = f"{DUTCH_WEEKDAYS[dt.weekday()]} {dt.day} {DUTCH_MONTHS[dt.month - 1]}"
    return date_str[0].upper() + date_str[1:]


def format_day_abbr_nl(dt: datetime) -> str:
    return DUTCH_WEEKDAYS_ABBR[dt.weekday()]


def format_time(dt: datetime, time_format: str, hour_only: bool = False) -> str:
    if time_format == "24h":
        return dt.strftime("%H:00" if hour_only else "%H:%M")
    fmt = "%I %p" if hour_only else "%I:%M %p"
    return dt.strftime(fmt).lstrip("0")


def get_moon_phase_name(phase_age: float) -> str:
    thresholds = [
        (1.0, "newmoon"), (7.0, "waxingcrescent"), (8.5, "firstquarter"),
        (14.0, "waxinggibbous"), (15.5, "fullmoon"), (22.0, "waninggibbous"),
        (23.5, "lastquarter"), (29.0, "waningcrescent"),
    ]
    for threshold, phase_name in thresholds:
        if phase_age <= threshold:
            return phase_name
    return "newmoon"


def get_moon_phase_icon_key(phase_name: str, lat: float) -> str:
    """Southern hemisphere sees waxing/waning and quarter phases mirrored."""
    if lat < 0:
        mirror = {
            "waxingcrescent": "waningcrescent", "waningcrescent": "waxingcrescent",
            "waxinggibbous": "waninggibbous", "waninggibbous": "waxinggibbous",
            "firstquarter": "lastquarter", "lastquarter": "firstquarter",
        }
        phase_name = mirror.get(phase_name, phase_name)
    return phase_name


def map_weather_code_to_icon(weather_code: int, is_day: int) -> str:
    icon = "01d"
    if weather_code in [0]:
        icon = "01d"
    elif weather_code in [1]:
        icon = "022d"
    elif weather_code in [2]:
        icon = "02d"
    elif weather_code in [3]:
        icon = "04d"
    elif weather_code in [51, 61, 80]:
        icon = "51d"
    elif weather_code in [53, 63, 81]:
        icon = "53d"
    elif weather_code in [55, 65, 82]:
        icon = "09d"
    elif weather_code in [45]:
        icon = "50d"
    elif weather_code in [48]:
        icon = "48d"
    elif weather_code in [56, 66]:
        icon = "56d"
    elif weather_code in [57, 67]:
        icon = "57d"
    elif weather_code in [71, 85]:
        icon = "71d"
    elif weather_code in [73]:
        icon = "73d"
    elif weather_code in [75, 86]:
        icon = "13d"
    elif weather_code in [77]:
        icon = "77d"
    elif weather_code in [95, 96, 99]:
        icon = "11d"

    if is_day == 0:
        icon = {"01d": "01n", "022d": "022n", "02d": "02n", "10d": "10n"}.get(icon, icon)
    return icon


def get_wind_direction_abbr_nl(wind_deg: float) -> str:
    directions = ["N", "NO", "O", "ZO", "Z", "ZW", "W", "NW"]
    return directions[round(wind_deg / 45) % 8]


def get_wind_icon_rotation(wind_deg: float) -> float:
    return (wind_deg + 180) % 360


def get_wind_speed_ms(speed: float, units: str) -> float:
    return speed * 0.44704 if units == "imperial" else speed


def get_beaufort_description_nl(speed_ms: float) -> str:
    levels = [
        (0.3, "Windstil"), (1.6, "Zwakke wind"), (3.4, "Zwakke wind"),
        (5.5, "Matige wind"), (8.0, "Matige wind"), (10.8, "Vrij krachtige wind"),
        (13.9, "Krachtige wind"), (17.2, "Harde wind"), (20.8, "Stormachtig"),
        (24.5, "Storm"), (28.5, "Zware storm"), (32.7, "Zeer zware storm"),
    ]
    for upper_bound, description in levels:
        if speed_ms < upper_bound:
            return description
    return "Orkaan"


def get_humidity_drop_count(humidity) -> int:
    try:
        humidity = float(humidity)
    except (TypeError, ValueError):
        return 1
    return min(5, max(1, math.ceil(humidity / 20)))


def get_pressure_gauge_rotation(pressure) -> float:
    try:
        pressure = float(pressure)
    except (TypeError, ValueError):
        pressure = 1013.25
    pressure_min, pressure_max = 970, 1050
    clamped = min(pressure_max, max(pressure_min, pressure))
    fraction = (clamped - pressure_min) / (pressure_max - pressure_min)
    return -90 + fraction * 180


def get_aqi_rotation_from_fraction(fraction_good: float) -> float:
    fraction_good = min(1.0, max(0.0, fraction_good))
    return -180 + (180 * fraction_good)


def get_european_aqi_rotation(aqi) -> float:
    try:
        aqi = float(aqi)
    except (TypeError, ValueError):
        return get_aqi_rotation_from_fraction(0.5)
    return get_aqi_rotation_from_fraction(1 - min(aqi, 100) / 100)


def get_uv_fraction(uv_index) -> float:
    try:
        uv_index = float(uv_index)
    except (TypeError, ValueError):
        uv_index = 0
    return min(1.0, max(0.0, uv_index / 11))


def get_uv_color(uv_index) -> str:
    low_color, high_color = (255, 179, 0), (216, 67, 21)
    fraction = get_uv_fraction(uv_index)
    r, g, b = (round(low + (high - low) * fraction) for low, high in zip(low_color, high_color))
    return f"#{r:02x}{g:02x}{b:02x}"


def get_uv_beam_points(uv_index, beam_count=10, cx=60, cy=60, core_r=24, min_len=10, max_len=32, half_width=5):
    """Returns beam_count triangles (each a list of 3 (x, y) points) in a 120x120 space."""
    beam_len = min_len + (max_len - min_len) * get_uv_fraction(uv_index)
    outer_r = core_r + beam_len
    beams = []
    for i in range(beam_count):
        angle = (2 * math.pi * i / beam_count) - (math.pi / 2)
        perp = angle + (math.pi / 2)
        base_x, base_y = cx + core_r * math.cos(angle), cy + core_r * math.sin(angle)
        left = (base_x + half_width * math.cos(perp), base_y + half_width * math.sin(perp))
        right = (base_x - half_width * math.cos(perp), base_y - half_width * math.sin(perp))
        tip = (cx + outer_r * math.cos(angle), cy + outer_r * math.sin(angle))
        beams.append([left, tip, right])
    return beams


@dataclass
class HourPoint:
    time_label: str
    temperature: int
    rain: float
    icon_key: str


@dataclass
class SunEvent:
    position: float  # fractional hour index into the hourly series
    icon_key: str     # "sunrise" | "sunset"


@dataclass
class DayForecast:
    day_label: str
    icon_key: str
    high: int
    low: int
    moon_phase_pct: str
    moon_icon_key: str


@dataclass
class WeatherSnapshot:
    current_date: str
    location: str
    current_icon_key: str
    current_temp: int
    feels_like: int
    temp_unit: str
    forecast_high: int
    forecast_low: int
    data_points: list = field(default_factory=list)   # list[dict], same shape as weather.py produced
    hourly: list = field(default_factory=list)          # list[HourPoint]
    sun_events: list = field(default_factory=list)      # list[SunEvent]
    daily: list = field(default_factory=list)           # list[DayForecast]
    last_refresh_time: str = ""


def get_nearest_location_name(lat: float, long: float) -> str:
    try:
        response = requests.get(
            NOMINATIM_REVERSE_URL.format(lat=lat, long=long),
            headers={"User-Agent": "PiWeatherDisplay"},
            timeout=10,
        )
        if not 200 <= response.status_code < 300:
            logger.warning(f"Failed to get nearest location name: {response.content}")
            return ""
        address = response.json().get("address", {})
        city = ""
        for key in ("city", "town", "village", "municipality", "hamlet", "suburb", "county"):
            if address.get(key):
                city = address[key]
                break
        country = address.get("country", "")
        if city and country:
            return f"{city}, {country}"
        return city or country
    except Exception as e:
        logger.warning(f"Could not retrieve nearest location name: {e}")
        return ""


def _get_open_meteo_data(lat, long, units, forecast_days):
    unit_params = OPEN_METEO_UNIT_PARAMS[units]
    url = OPEN_METEO_FORECAST_URL.format(lat=lat, long=long, forecast_days=forecast_days) + f"&{unit_params}"
    response = requests.get(url, timeout=30)
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"Failed to retrieve Open-Meteo weather data: {response.content}")
    return response.json()


def _get_open_meteo_air_quality(lat, long):
    url = OPEN_METEO_AIR_QUALITY_URL.format(lat=lat, long=long)
    response = requests.get(url, timeout=30)
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"Failed to retrieve Open-Meteo air quality data: {response.content}")
    return response.json()


def _parse_forecast(daily_data, units, tz, lat) -> list[DayForecast]:
    times = daily_data.get("time", [])
    weather_codes = daily_data.get("weathercode", [])
    temp_max = daily_data.get("temperature_2m_max", [])
    temp_min = daily_data.get("temperature_2m_min", [])
    if units == "standard":
        temp_max = [t + 273.15 for t in temp_max]
        temp_min = [t + 273.15 for t in temp_min]

    forecast = []
    for i in range(len(times)):
        dt = datetime.fromisoformat(times[i]).replace(tzinfo=timezone.utc).astimezone(tz)
        code = weather_codes[i] if i < len(weather_codes) else 0
        icon_key = map_weather_code_to_icon(code, is_day=1)

        target_date: date = dt.date() + timedelta(days=1)
        try:
            phase_age = moon.phase(target_date)
            phase_name = get_moon_phase_name(phase_age)
            lunar_cycle_days = 29.530588853
            phase_fraction = phase_age / lunar_cycle_days
            illum_pct = (1 - math.cos(2 * math.pi * phase_fraction)) / 2 * 100
        except Exception as e:
            logger.error(f"Error calculating moon phase for {target_date}: {e}")
            illum_pct = 0
            phase_name = "newmoon"
        moon_icon_key = get_moon_phase_icon_key(phase_name, lat)

        forecast.append(DayForecast(
            day_label=format_day_abbr_nl(dt),
            icon_key=icon_key,
            high=int(temp_max[i]) if i < len(temp_max) else 0,
            low=int(temp_min[i]) if i < len(temp_min) else 0,
            moon_phase_pct=f"{illum_pct:.0f}",
            moon_icon_key=moon_icon_key,
        ))
    return forecast


def _get_sun_events(start_epoch, end_epoch, sun_epoch_pairs) -> list[SunEvent]:
    events, seen = [], set()
    for sunrise_epoch, sunset_epoch in sun_epoch_pairs:
        for epoch, icon_key in [(sunrise_epoch, "sunrise"), (sunset_epoch, "sunset")]:
            if epoch and epoch not in seen and start_epoch <= epoch <= end_epoch:
                seen.add(epoch)
                events.append(SunEvent(position=(epoch - start_epoch) / 3600, icon_key=icon_key))
    return events


def _parse_hourly(hourly_data, units, tz, time_format, sunrises, sunsets) -> tuple[list[HourPoint], list[SunEvent]]:
    times = hourly_data.get("time", [])
    temperatures = hourly_data.get("temperature_2m", [])
    if units == "standard":
        temperatures = [t + 273.15 for t in temperatures]
    rain = hourly_data.get("precipitation", [])
    codes = hourly_data.get("weather_code", [])

    sun_map = {}
    for sr_s, ss_s in zip(sunrises, sunsets):
        sr_dt = datetime.fromisoformat(sr_s).astimezone(tz)
        ss_dt = datetime.fromisoformat(ss_s).astimezone(tz)
        sun_map[sr_dt.date()] = (sr_dt, ss_dt)

    current_time = datetime.now(tz)
    start_index = 0
    for i, time_str in enumerate(times):
        try:
            dt_hourly = datetime.fromisoformat(time_str).astimezone(tz)
            if dt_hourly.date() == current_time.date() and dt_hourly.hour >= current_time.hour:
                start_index = i
                break
            if dt_hourly.date() > current_time.date():
                break
        except ValueError:
            continue

    sliced_times = times[start_index:]
    sliced_temperatures = temperatures[start_index:]
    sliced_rain = rain[start_index:]
    sliced_codes = codes[start_index:]

    hourly = []
    for i in range(min(24, len(sliced_times))):
        dt = datetime.fromisoformat(sliced_times[i]).astimezone(tz)
        sunrise, sunset = sun_map.get(dt.date(), (None, None))
        is_day = 1 if sunrise and sunset and sunrise <= dt < sunset else 0
        code = sliced_codes[i] if i < len(sliced_codes) else 0
        hourly.append(HourPoint(
            time_label=format_time(dt, time_format, hour_only=True),
            temperature=int(sliced_temperatures[i]) if i < len(sliced_temperatures) else 0,
            rain=sliced_rain[i] if i < len(sliced_rain) else 0,
            icon_key=map_weather_code_to_icon(code, is_day),
        ))

    count = min(24, len(sliced_times))
    sun_events = []
    if count:
        start_dt = datetime.fromisoformat(sliced_times[0]).astimezone(tz)
        end_dt = datetime.fromisoformat(sliced_times[count - 1]).astimezone(tz)
        sun_epoch_pairs = [(sr.timestamp(), ss.timestamp()) for sr, ss in sun_map.values()]
        sun_events = _get_sun_events(start_dt.timestamp(), end_dt.timestamp(), sun_epoch_pairs)
    return hourly, sun_events


def _value_at_current_hour(times, values, tz, current_time):
    for i, time_str in enumerate(times):
        try:
            if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                return values[i] if i < len(values) else None
        except ValueError:
            continue
    return None


def _parse_data_points(weather_data, aqi_data, units, tz) -> list[dict]:
    data_points = []
    current_data = weather_data.get("current", {})
    hourly_data = weather_data.get("hourly", {})
    current_time = datetime.now(tz)

    wind_speed = current_data.get("windspeed", 0)
    wind_deg = current_data.get("winddirection", 0)
    data_points.append({
        "kind": "wind",
        "label": get_beaufort_description_nl(get_wind_speed_ms(wind_speed, units)),
        "measurement": wind_speed, "unit": UNITS[units]["speed"],
        "direction": get_wind_direction_abbr_nl(wind_deg),
        "rotation": get_wind_icon_rotation(wind_deg),
    })

    humidity = _value_at_current_hour(hourly_data.get("time", []), hourly_data.get("relative_humidity_2m", []), tz, current_time)
    humidity = int(humidity) if humidity is not None else "N/A"
    data_points.append({
        "kind": "humidity", "label": "Vochtigheid", "measurement": humidity, "unit": "%",
        "drop_count": get_humidity_drop_count(humidity),
    })

    pressure = _value_at_current_hour(hourly_data.get("time", []), hourly_data.get("surface_pressure", []), tz, current_time)
    pressure = int(pressure) if pressure is not None else "N/A"
    data_points.append({
        "kind": "pressure", "label": "Luchtdruk", "measurement": pressure, "unit": "hPa",
        "gauge_rotation": get_pressure_gauge_rotation(pressure),
    })

    uv_times = aqi_data.get("hourly", {}).get("time", [])
    uv_values = aqi_data.get("hourly", {}).get("uv_index", [])
    uv_index = _value_at_current_hour(uv_times, uv_values, tz, current_time)
    uv_index = uv_index if uv_index is not None else "N/A"
    data_points.append({
        "kind": "uv", "label": "UV-index", "measurement": uv_index, "unit": "",
        "uv_color": get_uv_color(uv_index), "uv_beams": get_uv_beam_points(uv_index),
    })

    if units == "imperial":
        visibility_conversion, visibility_max = 1 / 5280.0, 6.2
    else:
        visibility_conversion, visibility_max = 0.001, 10.0
    raw_visibility = _value_at_current_hour(hourly_data.get("time", []), hourly_data.get("visibility", []), tz, current_time)
    at_max_visibility = False
    if raw_visibility is not None:
        current_visibility = raw_visibility * visibility_conversion
        at_max_visibility = current_visibility >= visibility_max
        visibility_str = f"{current_visibility:.1f}"
        if at_max_visibility:
            visibility_str = "≥" + visibility_str
    else:
        visibility_str = "N/A"
    data_points.append({
        "kind": "visibility", "label": "Zicht", "measurement": visibility_str, "unit": UNITS[units]["distance"],
    })

    aqi_times = aqi_data.get("hourly", {}).get("time", [])
    aqi_values = aqi_data.get("hourly", {}).get("european_aqi", [])
    current_aqi = _value_at_current_hour(aqi_times, aqi_values, tz, current_time)
    scale = ""
    if current_aqi is not None:
        current_aqi = round(current_aqi, 1)
        scale = ["Goed", "Redelijk", "Matig", "Slecht", "Zeer slecht", "Extreem slecht"][min(int(current_aqi // 20), 5)]
    else:
        current_aqi = "N/A"
    data_points.append({
        "kind": "aqi", "label": "Luchtkwaliteit", "measurement": current_aqi, "unit": scale,
        "aqi_rotation": get_european_aqi_rotation(current_aqi),
    })

    return data_points


def fetch_snapshot(config: DisplayConfig) -> WeatherSnapshot:
    """Fetches current Open-Meteo data and returns a fully-parsed WeatherSnapshot."""
    weather_data = _get_open_meteo_data(config.latitude, config.longitude, config.units, config.forecast_days + 1)
    aqi_data = _get_open_meteo_air_quality(config.latitude, config.longitude)

    weather_timezone = weather_data.get("timezone")
    tz = pytz.timezone(weather_timezone) if weather_timezone else pytz.timezone(config.timezone)

    current = weather_data.get("current", {})
    daily = weather_data.get("daily", {})
    dt = datetime.fromisoformat(current.get("time")).astimezone(tz) if current.get("time") else datetime.now(tz)
    weather_code = current.get("weather_code", 0)
    is_day = current.get("is_day", 1)
    current_icon_key = map_weather_code_to_icon(weather_code, is_day)

    temperature_conversion = 273.15 if config.units == "standard" else 0.0

    daily_forecast = _parse_forecast(daily, config.units, tz, config.latitude)
    data_points = _parse_data_points(weather_data, aqi_data, config.units, tz)
    hourly, sun_events = _parse_hourly(
        weather_data.get("hourly", {}), config.units, tz, config.time_format,
        daily.get("sunrise", []), daily.get("sunset", []),
    )
    location = get_nearest_location_name(config.latitude, config.longitude)

    now = datetime.now(tz)
    last_refresh_time = now.strftime("%H:%M") if config.time_format == "24h" else now.strftime("%I:%M %p")

    return WeatherSnapshot(
        current_date=format_date_nl(dt),
        location=location,
        current_icon_key=current_icon_key,
        current_temp=round(current.get("temperature", 0) + temperature_conversion),
        feels_like=round(current.get("apparent_temperature", current.get("temperature", 0)) + temperature_conversion),
        temp_unit=UNITS[config.units]["temperature"],
        forecast_high=daily_forecast[0].high if daily_forecast else 0,
        forecast_low=daily_forecast[0].low if daily_forecast else 0,
        data_points=data_points,
        hourly=hourly,
        sun_events=sun_events,
        daily=daily_forecast[1:config.forecast_days + 1],
        last_refresh_time=last_refresh_time,
    )
