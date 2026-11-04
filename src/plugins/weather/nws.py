"""US National Weather Service (api.weather.gov) provider for the weather plugin.

Free, no API key, US locations only. Current conditions come from the nearest
NWS observing station (real measurements); forecasts are the NWS forecaster
grids. NWS does not publish UV index, air quality or sun times, so UV/AQ come
from Open-Meteo's air-quality API and sunrise/sunset are computed locally.

Produces the same template_params structure as the other providers.
"""

import logging
import math
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from plugins.weather import moon as astro

logger = logging.getLogger(__name__)

API = "https://api.weather.gov"
# NWS requires a User-Agent identifying the application.
HEADERS = {"User-Agent": "InkyPi weather plugin (github.com/fatihak/InkyPi)",
           "Accept": "application/geo+json"}
OBS_MAX_AGE = timedelta(hours=2)

_points_cache = {}


class NWSError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _get(url, params=None, retries=2):
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code} for {url}"
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        except requests.RequestException as e:
            last = f"{type(e).__name__} for {url}"
        time.sleep(3 * (attempt + 1))
    raise NWSError(last or f"Request failed: {url}")


def _points(lat, lon):
    key = (round(lat, 4), round(lon, 4))
    cached = _points_cache.get(key)
    if cached and time.time() - cached[0] < 24 * 3600:
        return cached[1]
    props = _get(f"{API}/points/{key[0]},{key[1]}").get("properties") or {}
    if not props.get("forecastHourly"):
        raise NWSError("Location not covered by the National Weather Service (US only).")
    _points_cache[key] = (time.time(), props)
    return props


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------

def _qv(obj):
    """(value, unitCode) from an NWS QuantitativeValue, or (None, '')."""
    if isinstance(obj, dict):
        return obj.get("value"), obj.get("unitCode") or obj.get("uom") or ""
    return None, ""


def _to_c(value, unit):
    if value is None:
        return None
    if unit.endswith("degF"):
        return (value - 32) * 5 / 9
    if unit.endswith("K"):
        return value - 273.15
    return value  # degC


def _temp_out(celsius, units):
    if celsius is None:
        return None
    if units == "imperial":
        return celsius * 9 / 5 + 32
    if units == "standard":
        return celsius + 273.15
    return celsius


def _speed_out(value, unit, units):
    """Wind speed to mph (imperial) or m/s (metric/standard)."""
    if value is None:
        return None
    if unit.endswith("km_h-1"):
        ms = value / 3.6
    elif unit.endswith("m_s-1"):
        ms = value
    elif unit.endswith("mi_h-1") or unit.endswith("mph"):
        ms = value * 0.44704
    elif unit.endswith("kn") or unit.endswith("kt"):
        ms = value * 0.514444
    else:
        ms = value / 3.6
    return ms * 2.236936 if units == "imperial" else ms


def _parse_wind_text(text):
    """'10 mph' / '5 to 10 mph' -> mph (upper value)."""
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text or "")]
    return max(nums) if nums else None


_DUR = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?")


def _valid_time(vt):
    """'2026-10-21T11:00:00+00:00/PT13H' -> (start, end) aware datetimes."""
    start_s, _, dur_s = vt.partition("/")
    start = datetime.fromisoformat(start_s)
    m = _DUR.fullmatch(dur_s or "PT1H")
    d, h, mi = (int(x) if x else 0 for x in (m.groups() if m else (0, 1, 0)))
    return start, start + timedelta(days=d, hours=h, minutes=mi)


def _grid_series(grid, name):
    layer = (grid or {}).get(name) or {}
    unit = layer.get("uom") or ""
    out = []
    for v in layer.get("values") or []:
        try:
            s, e = _valid_time(v["validTime"])
            out.append((s, e, v.get("value"), unit))
        except Exception:
            continue
    return out


# ---------------------------------------------------------------------------
# Icons: map NWS icon URLs to the plugin's icon set
# ---------------------------------------------------------------------------

_ICON_MAP = [
    # (NWS condition prefixes, plugin icon base)
    (("tsra", "tornado", "hurricane", "tropical_storm"), "11"),
    (("fzra", "rain_fzra", "snow_fzra"), "57"),
    (("rain_sleet", "snow_sleet", "sleet"), "77"),
    (("blizzard", "snow"), "13"),
    (("rain_snow",), "56"),
    (("rain_showers",), "10"),
    (("rain",), "53"),
    (("fog", "haze", "smoke", "dust"), "50"),
    (("ovc", "wind_ovc"), "04"),
    (("bkn", "wind_bkn"), "03"),
    (("sct", "wind_sct"), "02"),
    (("few", "wind_few"), "022"),
    (("skc", "wind_skc", "hot", "cold"), "01"),
]
_NIGHT_ICONS = {"01", "022", "02", "10"}


def icon_code(icon_url, is_day=None):
    """'https://api.weather.gov/icons/land/night/rain_showers,40?size=medium' -> '10n'."""
    url = (icon_url or "").split("?")[0]
    parts = url.split("/")
    if is_day is None:
        is_day = "night" not in parts
    # ".../land/night/rain_showers,40/tsra,60": conditions follow day|night;
    # two of them mean "then", so use the first (nearest in time).
    idx = next((i for i, p in enumerate(parts) if p in ("day", "night")), len(parts) - 2)
    cond = parts[idx + 1].split(",")[0] if idx + 1 < len(parts) else ""
    base = "02"
    for prefixes, code in _ICON_MAP:
        if any(cond == p or cond.startswith(p + "_") for p in prefixes):
            base = code
            break
    return f"{base}{'d' if is_day or base not in _NIGHT_ICONS else 'n'}"


# ---------------------------------------------------------------------------
# Fetch + parse
# ---------------------------------------------------------------------------

def _distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def _station_km(st, lat, lon):
    try:
        slon, slat = (st.get("geometry") or {}).get("coordinates")[:2]
        return _distance_km(lat, lon, slat, slon)
    except Exception:
        return float("inf")


def _latest_observation(points, lat, lon):
    try:
        stations = _get(points["observationStations"]).get("features") or []
    except Exception as e:
        logger.warning(f"NWS stations lookup failed: {e}")
        return None, None
    # NWS's list isn't strictly by distance, so sort by actual distance
    # from the configured location and use the nearest fresh reading.
    stations = sorted(stations, key=lambda st: _station_km(st, lat, lon))
    for st in stations[:4]:
        sid = (st.get("properties") or {}).get("stationIdentifier")
        if not sid:
            continue
        try:
            obs = _get(f"{API}/stations/{sid}/observations/latest").get("properties") or {}
        except Exception:
            continue
        ts = obs.get("timestamp")
        temp, _ = _qv(obs.get("temperature"))
        if ts and temp is not None:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(ts)
            if age <= OBS_MAX_AGE:
                km = _station_km(st, lat, lon)
                where = f"{sid} ({km * 0.621371:.1f} mi away)" if km != float("inf") else sid
                return where, obs
    return None, None


def fetch_and_parse(plugin, lat, lon, units, tz, time_format, aqi_data):
    points = _points(lat, lon)
    hourly = (_get(points["forecastHourly"]).get("properties") or {}).get("periods") or []
    daily = (_get(points["forecast"]).get("properties") or {}).get("periods") or []
    try:
        grid = _get(points["forecastGridData"]).get("properties") or {}
    except Exception as e:
        logger.warning(f"NWS grid data unavailable: {e}")
        grid = {}
    if not hourly:
        raise NWSError("NWS hourly forecast is empty.")
    station, obs = _latest_observation(points, lat, lon)
    logger.info(f"NWS: office {points.get('gridId')} grid {points.get('gridX')},{points.get('gridY')}"
                f" | observations from {station or 'none (using forecast)'}")

    now = datetime.now(tz)
    deg = "" if units == "standard" else "°"
    temp_unit = {"imperial": "°F", "metric": "°C", "standard": "K"}[units]

    def hourly_c(p):
        unit = "degF" if p.get("temperatureUnit") == "F" else "degC"
        t = p.get("temperature")
        if isinstance(t, dict):
            t, unit = _qv(t)
        return _to_c(t, unit)

    first = hourly[0]

    # ---- current conditions: station observation, else first hourly period
    cur_c = feels_c = None
    cur_icon = None
    if obs:
        cur_c = _to_c(*_qv(obs.get("temperature")))
        hi = _to_c(*_qv(obs.get("heatIndex")))
        wc = _to_c(*_qv(obs.get("windChill")))
        feels_c = hi if hi is not None else wc
        if obs.get("icon"):
            cur_icon = icon_code(obs["icon"])
    if cur_c is None:
        cur_c = hourly_c(first)
    if feels_c is None:
        feels_c = cur_c
    if not cur_icon:
        cur_icon = icon_code(first.get("icon"), first.get("isDaytime"))

    # ---- daily high/low from the forecaster grid (by local date), with a
    # fallback to the 12-hour forecast periods
    highs, lows = {}, {}
    for s, e, v, u in _grid_series(grid, "maxTemperature"):
        highs[s.astimezone(tz).date()] = _to_c(v, u)
    for s, e, v, u in _grid_series(grid, "minTemperature"):
        lows[(e - timedelta(minutes=1)).astimezone(tz).date()] = _to_c(v, u)  # overnight low -> morning date
    day_icons = {}
    for p in daily:
        d = datetime.fromisoformat(p["startTime"]).astimezone(tz).date()
        unit = "degF" if p.get("temperatureUnit") == "F" else "degC"
        t = _to_c(p.get("temperature"), unit)
        if p.get("isDaytime"):
            highs.setdefault(d, t)
            day_icons[d] = icon_code(p.get("icon"), True)
        else:
            lows.setdefault(d + timedelta(days=1), t)
            day_icons.setdefault(d, icon_code(p.get("icon"), True))

    today = now.date()
    today_hours = [hourly_c(p) for p in hourly
                   if datetime.fromisoformat(p["startTime"]).astimezone(tz).date() == today]
    if today not in highs:
        highs[today] = max([t for t in today_hours + [cur_c] if t is not None], default=cur_c)
    if today not in lows:
        lows[today] = min([t for t in today_hours + [cur_c] if t is not None], default=cur_c)

    def r(c):
        v = _temp_out(c, units)
        return round(v) if v is not None else "N/A"

    forecast = []
    for i in range(8):
        d = today + timedelta(days=i)
        if d not in highs and d not in lows:
            continue
        noon = datetime(d.year, d.month, d.day, 12, tzinfo=tz)
        pct, age, _w = astro.illumination(noon)
        phase = _moon_phase_name(age)
        forecast.append({
            "day": d.strftime("%a"),
            "high": r(highs.get(d)), "low": r(lows.get(d)),
            "icon": plugin.get_plugin_dir(f"icons/{day_icons.get(d, cur_icon[:-1] + 'd')}.png"),
            "moon_phase_pct": f"{pct:.0f}",
            "moon_phase_icon": plugin.get_moon_phase_icon_path(phase, lat),
        })

    # ---- hourly chart (24 h): temperature, precipitation chance, rain amount
    qpf = _grid_series(grid, "quantitativePrecipitation")
    hourly_out = []
    for p in hourly[:24]:
        start = datetime.fromisoformat(p["startTime"])
        amount_mm = 0.0
        for s, e, v, u in qpf:
            if v and s <= start < e:
                hours = max(1.0, (e - s).total_seconds() / 3600)
                amount_mm = v / hours  # spread the period's total evenly
                break
        pop, _ = _qv(p.get("probabilityOfPrecipitation"))
        hourly_out.append({
            "time": plugin.format_time(start.astimezone(tz), time_format, hour_only=True),
            "temperature": int(round(_temp_out(hourly_c(p), units))),
            "precipitation": (pop or 0) / 100,
            "rain": round(amount_mm / 25.4 if units == "imperial" else amount_mm, 2),
            "icon": plugin.get_plugin_dir(f"icons/{icon_code(p.get('icon'), p.get('isDaytime'))}.png"),
        })

    # ---- metrics
    points_out = []
    midnight = datetime(today.year, today.month, today.day, tzinfo=tz)
    sunrise, sunset = astro.sun_times(midnight, lat, lon)
    for label, when, icon in (("Sunrise", sunrise, "sunrise"), ("Sunset", sunset, "sunset")):
        if when:
            when = (when + timedelta(seconds=30)).replace(second=0, microsecond=0)
            points_out.append({
                "label": label,
                "measurement": plugin.format_time(when, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else when.strftime("%p"),
                "icon": plugin.get_plugin_dir(f"icons/{icon}.png"),
            })

    speed_unit = {"imperial": "mph", "metric": "m/s", "standard": "m/s"}[units]
    wind = wind_deg = None
    if obs:
        wind = _speed_out(*_qv(obs.get("windSpeed")), units)
        wind_deg, _ = _qv(obs.get("windDirection"))
    if wind is None:
        mph = _parse_wind_text(first.get("windSpeed"))
        wind = mph if units == "imperial" else (mph * 0.44704 if mph is not None else None)
    if wind_deg is None:
        compass = {"N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5, "SE": 135,
                   "SSE": 157.5, "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5, "W": 270,
                   "WNW": 292.5, "NW": 315, "NNW": 337.5}
        wind_deg = compass.get((first.get("windDirection") or "").upper(), 0)
    points_out.append({
        "label": "Wind", "measurement": round(wind, 1) if wind is not None else "N/A",
        "unit": speed_unit, "icon": plugin.get_plugin_dir("icons/wind.png"),
        "arrow": plugin.get_wind_arrow(wind_deg or 0),
    })

    hum = _qv(obs.get("relativeHumidity"))[0] if obs else None
    if hum is None:
        hum = _qv(first.get("relativeHumidity"))[0]
    points_out.append({"label": "Humidity", "measurement": int(round(hum)) if hum is not None else "N/A",
                       "unit": "%", "icon": plugin.get_plugin_dir("icons/humidity.png")})

    pres_pa = (_qv(obs.get("seaLevelPressure"))[0] or _qv(obs.get("barometricPressure"))[0]) if obs else None
    points_out.append({"label": "Pressure", "measurement": int(round(pres_pa / 100)) if pres_pa else "N/A",
                       "unit": "hPa", "icon": plugin.get_plugin_dir("icons/pressure.png")})

    points_out.extend(_uv_and_air_quality(plugin, aqi_data, tz, now))

    vis_m = _qv(obs.get("visibility"))[0] if obs else None
    if vis_m is not None:
        vis = vis_m / 1609.344 if units == "imperial" else vis_m / 1000
        vis_s = f"{vis:.1f}"
    else:
        vis_s = "N/A"
    points_out.insert(len(points_out) - 1, {
        "label": "Visibility", "measurement": vis_s,
        "unit": "mi" if units == "imperial" else "km",
        "icon": plugin.get_plugin_dir("icons/visibility.png"),
    })

    return {
        "current_date": now.strftime("%A, %B %d"),
        "current_day_icon": plugin.get_plugin_dir(f"icons/{cur_icon}.png"),
        "current_temperature": str(r(cur_c)),
        "feels_like": str(r(feels_c)),
        "temperature_unit": temp_unit,
        "units": units,
        "time_format": time_format,
        "forecast": forecast,
        "data_points": points_out,
        "hourly_forecast": hourly_out,
        "nws_location": ((points.get("relativeLocation") or {}).get("properties") or {}),
        "nws_timezone": points.get("timeZone"),
    }


def _moon_phase_name(age_days):
    from plugins.weather.weather import get_moon_phase_name
    return get_moon_phase_name(age_days * 28.0 / astro.SYNODIC_MONTH)


def _uv_and_air_quality(plugin, aqi_data, tz, now):
    """UV (current / today's max) and air quality from Open-Meteo's air-quality data."""
    hourly = (aqi_data or {}).get("hourly", {})
    times = hourly.get("time", [])
    uv_vals, aqi_vals = hourly.get("uv_index", []), hourly.get("european_aqi", [])
    cur_uv = cur_aqi = "N/A"
    today_uv = []
    for i, t in enumerate(times):
        try:
            dt = datetime.fromisoformat(t)
            dt = dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)
        except ValueError:
            continue
        if dt.date() == now.date():
            if i < len(uv_vals) and uv_vals[i] is not None:
                today_uv.append(uv_vals[i])
            if dt.hour == now.hour:
                if i < len(uv_vals):
                    cur_uv = uv_vals[i]
                if i < len(aqi_vals) and aqi_vals[i] is not None:
                    cur_aqi = round(aqi_vals[i], 1)
    uv_max = max(today_uv) if today_uv else None
    scale = ""
    if cur_aqi != "N/A":
        scale = ["Good", "Fair", "Moderate", "Poor", "Very Poor", "Ext Poor"][min(int(cur_aqi // 20), 5)]
    return [
        {"label": "UV Index", "measurement": plugin.format_uv(cur_uv),
         "unit": plugin.format_uv_max(uv_max), "uv_max": uv_max,
         "icon": plugin.get_plugin_dir("icons/uvi.png")},
        {"label": "Air Quality", "measurement": cur_aqi, "unit": scale,
         "icon": plugin.get_plugin_dir("icons/aqi.png")},
    ]
