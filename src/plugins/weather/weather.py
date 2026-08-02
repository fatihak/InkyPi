from plugins.base_plugin.base_plugin import BasePlugin
import requests
import logging
from datetime import datetime, timedelta, timezone, date
from astral import moon
import pytz
from io import BytesIO
import math

logger = logging.getLogger(__name__)

DUTCH_WEEKDAYS = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
DUTCH_WEEKDAYS_ABBR = ["ma", "di", "wo", "do", "vr", "za", "zo"]
DUTCH_MONTHS = [
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december"
]

def format_date_nl(dt):
    date_str = f"{DUTCH_WEEKDAYS[dt.weekday()]} {dt.day} {DUTCH_MONTHS[dt.month - 1]}"
    return date_str[0].upper() + date_str[1:]

def format_day_abbr_nl(dt):
    return DUTCH_WEEKDAYS_ABBR[dt.weekday()]

def get_moon_phase_name(phase_age: float) -> str:
    """Determines the name of the lunar phase based on the age of the moon."""
    PHASES_THRESHOLDS = [
        (1.0, "newmoon"),
        (7.0, "waxingcrescent"),
        (8.5, "firstquarter"),
        (14.0, "waxinggibbous"),
        (15.5, "fullmoon"),
        (22.0, "waninggibbous"),
        (23.5, "lastquarter"),
        (29.0, "waningcrescent"),
    ]

    for threshold, phase_name in PHASES_THRESHOLDS:
        if phase_age <= threshold:
            return phase_name  
    return "newmoon"

UNITS = {
    "standard": {
        "temperature": "K",
        "speed": "m/s",
        "distance":"km"
    },
    "metric": {
        "temperature": "°C",
        "speed": "m/s",
        "distance":"km"

    },
    "imperial": {
        "temperature": "°F",
        "speed": "mph",
        "distance":"mi"
    }
}

WEATHER_URL = "https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={long}&units={units}&exclude=minutely&appid={api_key}"
AIR_QUALITY_URL = "http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={long}&appid={api_key}"
GEOCODING_URL = "http://api.openweathermap.org/geo/1.0/reverse?lat={lat}&lon={long}&limit=1&appid={api_key}"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={long}&format=jsonv2&accept-language=en&zoom=14"

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={long}&hourly=weather_code,temperature_2m,precipitation,precipitation_probability,relative_humidity_2m,surface_pressure,visibility&daily=weathercode,temperature_2m_max,temperature_2m_min,sunrise,sunset&current=temperature,windspeed,winddirection,is_day,precipitation,weather_code,apparent_temperature&timezone=auto&models=best_match&forecast_days={forecast_days}"
OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={long}&hourly=european_aqi,uv_index,uv_index_clear_sky&timezone=auto"
OPEN_METEO_UNIT_PARAMS = {
    "standard": "temperature_unit=celsius&wind_speed_unit=ms&precipitation_unit=mm",  # temperature is converted to Kelvin later
    "metric":   "temperature_unit=celsius&wind_speed_unit=ms&precipitation_unit=mm",
    "imperial": "temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
}

class Weather(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "OpenWeatherMap",
            "expected_key": "OPEN_WEATHER_MAP_SECRET"
        }
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        lat_str = settings.get('latitude')
        long_str = settings.get('longitude')
        if not lat_str or not long_str:
            raise RuntimeError("Latitude and Longitude are required.")
        lat = float(lat_str)
        long = float(long_str)

        units = settings.get('units')
        if not units or units not in ['metric', 'imperial', 'standard']:
            raise RuntimeError("Units are required.")

        weather_provider = settings.get('weatherProvider', 'OpenWeatherMap')
        title = settings.get('customTitle', '')

        timezone = device_config.get_config("timezone", default="America/New_York")
        time_format = device_config.get_config("time_format", default="12h")
        tz = pytz.timezone(timezone)

        try:
            if weather_provider == "OpenWeatherMap":
                api_key = device_config.load_env_key("OPEN_WEATHER_MAP_SECRET")
                if not api_key:
                    raise RuntimeError("Open Weather Map API Key not configured.")
                weather_data = self.get_weather_data(api_key, units, lat, long)
                aqi_data = self.get_air_quality(api_key, lat, long)
                if settings.get('titleSelection', 'location') == 'location':
                    title = self.get_location(api_key, lat, long)
                if settings.get('weatherTimeZone', 'locationTimeZone') == 'locationTimeZone':
                    logger.info("Using location timezone for OpenWeatherMap data.")
                    wtz = self.parse_timezone(weather_data)
                    template_params = self.parse_weather_data(weather_data, aqi_data, wtz, units, time_format, lat)
                else:
                    logger.info("Using configured timezone for OpenWeatherMap data.")
                    template_params = self.parse_weather_data(weather_data, aqi_data, tz, units, time_format, lat)
            elif weather_provider == "OpenMeteo":
                forecast_days = 7
                weather_data = self.get_open_meteo_data(lat, long, units, forecast_days + 1)
                aqi_data = self.get_open_meteo_air_quality(lat, long)
                if settings.get('weatherTimeZone', 'locationTimeZone') == 'locationTimeZone':
                    logger.info("Using location timezone for Open-Meteo data.")
                    wtz = self.parse_timezone(weather_data)
                    template_params = self.parse_open_meteo_data(weather_data, aqi_data, wtz, units, time_format, lat)
                else:
                    logger.info("Using configured timezone for Open-Meteo data.")
                    template_params = self.parse_open_meteo_data(weather_data, aqi_data, tz, units, time_format, lat)
            else:
                raise RuntimeError(f"Unknown weather provider: {weather_provider}")

            template_params['title'] = title
        except Exception as e:
            logger.error(f"{weather_provider} request failed: {str(e)}")
            raise RuntimeError(f"{weather_provider} request failure, please check logs.")
       
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        template_params["plugin_settings"] = settings
        template_params["nearest_location"] = self.get_nearest_location_name(lat, long)

        # Add last refresh time
        now = datetime.now(tz)
        if time_format == "24h":
            last_refresh_time = now.strftime("%Y-%m-%d %H:%M")
        else:
            last_refresh_time = now.strftime("%Y-%m-%d %I:%M %p")
        template_params["last_refresh_time"] = last_refresh_time

        image = self.render_image(dimensions, "weather.html", "weather.css", template_params)

        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")
        return image

    def parse_weather_data(self, weather_data, aqi_data, tz, units, time_format, lat):
        current = weather_data.get("current")
        daily_forecast = weather_data.get("daily", [])
        dt = datetime.fromtimestamp(current.get('dt'), tz=timezone.utc).astimezone(tz)
        current_icon = current.get("weather")[0].get("icon")
        icon_codes_to_preserve = ["01", "02", "10"]
        icon_code = current_icon[:2]
        current_suffix = current_icon[-1]

        if icon_code not in icon_codes_to_preserve:
            if current_icon.endswith('n'):
                current_icon = current_icon.replace("n", "d")
        data = {
            "current_date": format_date_nl(dt),
            "current_day_icon": self.get_plugin_dir(f'icons/{current_icon}.png'),
            "current_temperature": str(round(current.get("temp"))),
            "feels_like": str(round(current.get("feels_like"))),
            "temperature_unit": UNITS[units]["temperature"],
            "units": units,
            "time_format": time_format
        }
        data['forecast'] = self.parse_forecast(weather_data.get('daily'), tz, current_suffix, lat)
        data['data_points'] = self.parse_data_points(weather_data, aqi_data, tz, units, time_format)

        data['hourly_forecast'], data['sun_events'] = self.parse_hourly(weather_data.get('hourly'), tz, time_format, units, daily_forecast)
        return data

    def parse_open_meteo_data(self, weather_data, aqi_data, tz, units, time_format, lat):
        current = weather_data.get("current", {})
        daily = weather_data.get('daily', {})
        dt = datetime.fromisoformat(current.get('time')).astimezone(tz) if current.get('time') else datetime.now(tz)
        weather_code = current.get("weather_code", 0)
        is_day = current.get("is_day", 1)
        current_icon = self.map_weather_code_to_icon(weather_code, is_day)
        
        temperature_conversion = 273.15 if units == "standard" else 0.

        data = {
            "current_date": format_date_nl(dt),
            "current_day_icon": self.get_plugin_dir(f'icons/{current_icon}.png'),
            "current_temperature": str(round(current.get("temperature", 0) + temperature_conversion)),
            "feels_like": str(round(current.get("apparent_temperature", current.get("temperature", 0)) + temperature_conversion)),
            "temperature_unit": UNITS[units]["temperature"],
            "units": units,
            "time_format": time_format
        }

        data['forecast'] = self.parse_open_meteo_forecast(weather_data.get('daily', {}), units, tz, is_day, lat)
        data['data_points'] = self.parse_open_meteo_data_points(weather_data, aqi_data, units, tz, time_format)
        
        data['hourly_forecast'], data['sun_events'] = self.parse_open_meteo_hourly(weather_data.get('hourly', {}), units, tz, time_format, daily.get('sunrise', []), daily.get('sunset', []))
        return data

    def map_weather_code_to_icon(self, weather_code, is_day):

        icon = "01d" # Default to clear day icon
        
        if weather_code in [0]:   # Clear sky
            icon = "01d"
        elif weather_code in [1]: # Mainly clear
            icon = "022d"
        elif weather_code in [2]: # Partly cloudy
            icon = "02d"
        elif weather_code in [3]: # Overcast
            icon = "04d"
        elif weather_code in [51, 61, 80]: # Drizzle, showers, rain: Light
            icon = "51d"          
        elif weather_code in [53, 63, 81]: # Drizzle, showers, rain: Moderatr
            icon = "53d"
        elif weather_code in [55, 65, 82]: # Drizzle, showers, rain: Heavy
            icon = "09d"
        elif weather_code in [45]: # Fog
            icon = "50d"                       
        elif weather_code in [48]: # Icy fog
            icon = "48d"
        elif weather_code in [56, 66]: # Light freezing Drizzle
            icon = "56d"            
        elif weather_code in [57, 67]: # Freezing Drizzle
            icon = "57d"            
        elif weather_code in [71, 85]: # Snow fall: Slight
            icon = "71d"
        elif weather_code in [73]:     # Snow fall: Moderate
            icon = "73d"
        elif weather_code in [75, 86]: # Snow fall: Heavy
            icon = "13d"
        elif weather_code in [77]:     # Snow grain
            icon = "77d"
        elif weather_code in [95]: # Thunderstorm
            icon = "11d"
        elif weather_code in [96, 99]: # Thunderstorm with slight and heavy hail
            icon = "11d"

        if is_day == 0:
            if icon == "01d":
                icon = "01n"      # Clear sky night
            elif icon == "022d":
                icon = "022n"     # Mainly clear night
            elif icon == "02d":
                icon = "02n"      # Partly cloudy night                
            elif icon == "10d":
                icon = "10n"      # Rain night

        return icon

    def get_moon_phase_icon_path(self, phase_name: str, lat: float) -> str:
        """Determines the path to the moon icon, inverting it if the location is in the Southern Hemisphere."""
        # Waxing, Waning, First and Last quarter phases are inverted between hemispheres.
        if lat < 0: # Southern Hemisphere
            if phase_name == "waxingcrescent":
                phase_name = "waningcrescent"
            elif phase_name == "waxinggibbous":
                phase_name = "waninggibbous"
            elif phase_name == "waningcrescent":
                phase_name = "waxingcrescent"
            elif phase_name == "waninggibbous":
                phase_name = "waxinggibbous"
            elif phase_name == "firstquarter":
                phase_name = "lastquarter"
            elif phase_name == "lastquarter":
                phase_name = "firstquarter"
        
        return self.get_plugin_dir(f"icons/{phase_name}.png")

    def parse_forecast(self, daily_forecast, tz, current_suffix, lat):
        """
        - daily_forecast: list of daily entries from One‑Call v3 (each has 'dt', 'weather', 'temp', 'moon_phase')
        - tz: your target tzinfo (e.g. from zoneinfo or pytz)
        """
        PHASES = [
            (0.0, "newmoon"),
            (0.25, "firstquarter"),
            (0.5, "fullmoon"),
            (0.75, "lastquarter"),
            (1.0, "newmoon"),
        ]

        def choose_phase_name(phase: float) -> str:
            for target, name in PHASES:
                if math.isclose(phase, target, abs_tol=1e-3):
                    return name
            if 0.0 < phase < 0.25:
                return "waxingcrescent"
            elif 0.25 < phase < 0.5:
                return "waxinggibbous"
            elif 0.5 < phase < 0.75:
                return "waninggibbous"
            else:
                return "waningcrescent"

        forecast = []
        icon_codes_to_apply_current_suffix = ["01", "02", "10"]
        for day in daily_forecast:
            # --- weather icon ---
            weather_icon = day["weather"][0]["icon"]  # e.g. "10d", "01n"
            icon_code = weather_icon[:2]
            if icon_code in icon_codes_to_apply_current_suffix:
                weather_icon_base = weather_icon[:-1]
                weather_icon = weather_icon_base + current_suffix
            else:
                if weather_icon.endswith('n'):
                    weather_icon = weather_icon.replace("n", "d")
            weather_icon = f"{icon_code}d"        
            weather_icon_path = self.get_plugin_dir(f"icons/{weather_icon}.png")

            # --- moon phase & icon ---
            moon_phase = float(day["moon_phase"])  # [0.0–1.0]
            phase_name_north_hemi = choose_phase_name(moon_phase)
            moon_icon_path = self.get_moon_phase_icon_path(phase_name_north_hemi, lat)
            # --- true illumination percent, no decimals ---
            illum_fraction = (1 - math.cos(2 * math.pi * moon_phase)) / 2
            moon_pct = f"{illum_fraction * 100:.0f}"

            # --- date & temps ---
            dt = datetime.fromtimestamp(day["dt"], tz=timezone.utc).astimezone(tz)
            day_label = format_day_abbr_nl(dt)

            forecast.append(
                {
                    "day": day_label,
                    "high": int(day["temp"]["max"]),
                    "low": int(day["temp"]["min"]),
                    "icon": weather_icon_path,
                    "moon_phase_pct": moon_pct,
                    "moon_phase_icon": moon_icon_path,
                }
            )

        return forecast
        
    def parse_open_meteo_forecast(self, daily_data, units, tz, is_day, lat):
        """
        Parse the daily forecast from Open-Meteo API and calculate moon phase and illumination using the local 'astral' library.
        """
        times = daily_data.get('time', [])
        weather_codes = daily_data.get('weathercode', [])
        temp_max = daily_data.get('temperature_2m_max', [])
        temp_min = daily_data.get('temperature_2m_min', [])
        if units == "standard":
            temp_max = [T + 273.15 for T in temp_max]
            temp_min = [T + 273.15 for T in temp_min]

        forecast = []

        for i in range(0, len(times)): 
            dt = datetime.fromisoformat(times[i]).replace(tzinfo=timezone.utc).astimezone(tz)
            day_label = format_day_abbr_nl(dt)

            code = weather_codes[i] if i < len(weather_codes) else 0
            weather_icon = self.map_weather_code_to_icon(code, is_day=1)
            weather_icon_path = self.get_plugin_dir(f"icons/{weather_icon}.png")

            timestamp = int(dt.replace(hour=12, minute=0, second=0).timestamp())
            target_date: date = dt.date() + timedelta(days=1)

            try:
                phase_age = moon.phase(target_date)
                phase_name_north_hemi = get_moon_phase_name(phase_age)
                LUNAR_CYCLE_DAYS = 29.530588853
                phase_fraction = phase_age / LUNAR_CYCLE_DAYS
                illum_pct = (1 - math.cos(2 * math.pi * phase_fraction)) / 2 * 100
            except Exception as e:
                logger.error(f"Error calculating moon phase for {target_date}: {e}")
                illum_pct = 0
                phase_name_north_hemi = "newmoon"
            moon_icon_path = self.get_moon_phase_icon_path(phase_name_north_hemi, lat)

            forecast.append({
                "day": day_label,
                "high": int(temp_max[i]) if i < len(temp_max) else 0,
                "low": int(temp_min[i]) if i < len(temp_min) else 0,
                "icon": weather_icon_path,
                "moon_phase_pct": f"{illum_pct:.0f}",
                "moon_phase_icon": moon_icon_path
            })

        return forecast

    def parse_hourly(self, hourly_forecast, tz, time_format, units, daily_forecast):
        hourly = []
        icon_codes_to_preserve = ["01", "02", "10"]
        
        sun_map = {}
        for day in daily_forecast:
            day_date = datetime.fromtimestamp(day['dt'], tz=timezone.utc).astimezone(tz).date()
            sun_map[day_date] = (day['sunrise'], day['sunset'])
        
        for hour in hourly_forecast[:24]:
            dt_epoch = hour.get('dt')
            dt = datetime.fromtimestamp(dt_epoch, tz=timezone.utc).astimezone(tz)
            rain_mm = hour.get("rain", {}).get("1h", 0.0)
            snow_mm = hour.get("snow", {}).get("1h", 0.0)
            total_precip_mm = rain_mm + snow_mm
            sunrise, sunset = sun_map.get(dt.date(), (0, 0))
        
            is_day = sunrise <= dt_epoch < sunset
            suffix = 'd' if is_day else 'n'
        
            raw_icon = hour.get("weather", [{}])[0].get("icon", "01d")
            icon_base = raw_icon[:2]
            icon_name = f"{icon_base}{suffix}" if icon_base in icon_codes_to_preserve else f"{icon_base}d"
            
            if units == "imperial":
                precip_value = total_precip_mm / 25.4
            else:
                precip_value = total_precip_mm 
            hour_forecast = {
                "time": self.format_time(dt, time_format, hour_only=True),
                "temperature": int(hour.get("temp")),
                "precipitation": hour.get("pop"),
                "rain": round(precip_value, 2),
                "icon": self.get_plugin_dir(f'icons/{icon_name}.png')
            }
            hourly.append(hour_forecast)

        hours = hourly_forecast[:24]
        sun_events = []
        if hours:
            sun_events = self.get_sun_events(hours[0].get('dt'), hours[-1].get('dt'), sun_map.values())
        return hourly, sun_events

    def get_sun_events(self, start_epoch, end_epoch, sun_epoch_pairs):
        """Finds sunrise/sunset epochs (as unix timestamps) that fall within the hourly
        window and returns their fractional position along it, for placement on the
        hourly chart's x-axis (e.g. 2.5 means halfway between the 3rd and 4th hour)."""
        events = []
        seen = set()
        for sunrise_epoch, sunset_epoch in sun_epoch_pairs:
            for epoch, icon_name in [(sunrise_epoch, 'sunrise'), (sunset_epoch, 'sunset')]:
                if epoch and epoch not in seen and start_epoch <= epoch <= end_epoch:
                    seen.add(epoch)
                    events.append({
                        "position": (epoch - start_epoch) / 3600,
                        "icon": self.get_plugin_dir(f'icons/{icon_name}.png')
                    })
        return events

    def parse_open_meteo_hourly(self, hourly_data, units, tz, time_format, sunrises, sunsets):
        hourly = []
        times = hourly_data.get('time', [])
        temperatures = hourly_data.get('temperature_2m', [])
        if units == "standard":
            temperatures = [temperature + 273.15 for temperature in temperatures]
        precipitation_probabilities = hourly_data.get('precipitation_probability', [])
        rain = hourly_data.get('precipitation', [])
        codes = hourly_data.get('weather_code', [])
        
        sun_map = {}
        for sr_s, ss_s in zip(sunrises, sunsets):
            sr_dt = datetime.fromisoformat(sr_s).astimezone(tz)
            ss_dt = datetime.fromisoformat(ss_s).astimezone(tz)
            sun_map[sr_dt.date()] = (sr_dt, ss_dt)
        
        current_time_in_tz = datetime.now(tz)
        start_index = 0
        for i, time_str in enumerate(times):
            try:
                dt_hourly = datetime.fromisoformat(time_str).astimezone(tz)
                if dt_hourly.date() == current_time_in_tz.date() and dt_hourly.hour >= current_time_in_tz.hour:
                    start_index = i
                    break
                if dt_hourly.date() > current_time_in_tz.date():
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} in hourly data.")
                continue

        sliced_times = times[start_index:]
        sliced_temperatures = temperatures[start_index:]
        sliced_precipitation_probabilities = precipitation_probabilities[start_index:]
        sliced_rain = rain[start_index:]
        sliced_codes = codes[start_index:]

        for i in range(min(24, len(sliced_times))):
            dt = datetime.fromisoformat(sliced_times[i]).astimezone(tz)
            sunrise, sunset = sun_map.get(dt.date(), (None, None))
            is_day = 0
            if sunrise and sunset:
                is_day = 1 if sunrise <= dt < sunset else 0
            code = sliced_codes[i] if i < len(sliced_codes) else 0
            icon_name = self.map_weather_code_to_icon(code, is_day)
            hour_forecast = {
                "time": self.format_time(dt, time_format, True),
                "temperature": int(sliced_temperatures[i]) if i < len(sliced_temperatures) else 0,
                "precipitation": (sliced_precipitation_probabilities[i] / 100) if i < len(sliced_precipitation_probabilities) else 0,
                "rain": (sliced_rain[i]) if i < len(sliced_rain) else 0,
                "icon": self.get_plugin_dir(f"icons/{icon_name}.png")
            }
            hourly.append(hour_forecast)

        sliced_dt_count = min(24, len(sliced_times))
        sun_events = []
        if sliced_dt_count:
            start_dt = datetime.fromisoformat(sliced_times[0]).astimezone(tz)
            end_dt = datetime.fromisoformat(sliced_times[sliced_dt_count - 1]).astimezone(tz)
            sun_epoch_pairs = [(sr.timestamp(), ss.timestamp()) for sr, ss in sun_map.values()]
            sun_events = self.get_sun_events(start_dt.timestamp(), end_dt.timestamp(), sun_epoch_pairs)
        return hourly, sun_events

    def parse_data_points(self, weather, air_quality, tz, units, time_format):
        data_points = []

        wind_deg = weather.get('current', {}).get("wind_deg", 0)
        wind_speed = weather.get('current', {}).get("wind_speed")
        data_points.append({
            "label": self.get_beaufort_description_nl(self.get_wind_speed_ms(wind_speed, units)),
            "measurement": wind_speed,
            "unit": UNITS[units]["speed"],
            "direction": self.get_wind_direction_abbr_nl(wind_deg),
            "rotation": self.get_wind_icon_rotation(wind_deg),
            "is_wind": True
        })

        humidity = weather.get('current', {}).get("humidity")
        data_points.append({
            "label": "Vochtigheid",
            "measurement": humidity,
            "unit": '%',
            "is_humidity": True,
            "drop_count": self.get_humidity_drop_count(humidity)
        })

        pressure = weather.get('current', {}).get("pressure")
        data_points.append({
            "label": "Luchtdruk",
            "measurement": pressure,
            "unit": 'hPa',
            "is_pressure": True,
            "gauge_rotation": self.get_pressure_gauge_rotation(pressure)
        })

        uvi = weather.get('current', {}).get("uvi")
        data_points.append({
            "label": "UV-index",
            "measurement": uvi,
            "unit": '',
            "is_uv": True,
            "uv_color": self.get_uv_color(uvi),
            "uv_beams": self.get_uv_beam_points(uvi)
        })

        visibility = weather.get('current', {}).get("visibility")
        if units == "imperial":
            # convert from m to mi
            visibility /= 1609.
            at_max_visibility = visibility >= 6.2
        else:
            # convert from m to km
            visibility /= 1000.
            at_max_visibility = visibility >= 10
        visibility_str = f"{visibility:.1f}"
        if at_max_visibility:
            visibility_str = u"\u2265" + visibility_str
        data_points.append({
            "label": "Zicht",
            "measurement": visibility_str,
            "unit": UNITS[units]["distance"],
            "icon": self.get_plugin_dir('icons/visibility.png')
        })

        aqi = air_quality.get('list', [])[0].get("main", {}).get("aqi")
        data_points.append({
            "label": "Luchtkwaliteit",
            "measurement": aqi,
            "unit": ["Goed", "Redelijk", "Matig", "Slecht", "Zeer slecht"][int(aqi)-1],
            "is_aqi": True,
            "aqi_rotation": self.get_owm_aqi_rotation(aqi)
        })

        return data_points

    def parse_open_meteo_data_points(self, weather_data, aqi_data, units, tz, time_format):
        """Parses current data points from Open-Meteo API response."""
        data_points = []
        daily_data = weather_data.get('daily', {})
        current_data = weather_data.get('current', {})
        hourly_data = weather_data.get('hourly', {})

        current_time = datetime.now(tz)

        # Wind
        wind_speed = current_data.get("windspeed", 0)
        wind_deg = current_data.get("winddirection", 0)
        wind_unit = UNITS[units]["speed"]
        data_points.append({
            "label": self.get_beaufort_description_nl(self.get_wind_speed_ms(wind_speed, units)),
            "measurement": wind_speed, "unit": wind_unit,
            "direction": self.get_wind_direction_abbr_nl(wind_deg),
            "rotation": self.get_wind_icon_rotation(wind_deg),
            "is_wind": True
        })

        # Humidity
        current_humidity = "N/A"
        humidity_hourly_times = hourly_data.get('time', [])
        humidity_values = hourly_data.get('relative_humidity_2m', [])
        for i, time_str in enumerate(humidity_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_humidity = int(humidity_values[i])
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for humidity.")
                continue
        data_points.append({
            "label": "Vochtigheid", "measurement": current_humidity, "unit": '%',
            "is_humidity": True,
            "drop_count": self.get_humidity_drop_count(current_humidity)
        })

        # Pressure
        current_pressure = "N/A"
        pressure_hourly_times = hourly_data.get('time', [])
        pressure_values = hourly_data.get('surface_pressure', [])
        for i, time_str in enumerate(pressure_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_pressure = int(pressure_values[i])
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for pressure.")
                continue
        data_points.append({
            "label": "Luchtdruk", "measurement": current_pressure, "unit": 'hPa',
            "is_pressure": True,
            "gauge_rotation": self.get_pressure_gauge_rotation(current_pressure)
        })

        # UV Index
        uv_index_hourly_times = aqi_data.get('hourly', {}).get('time', [])
        uv_index_values = aqi_data.get('hourly', {}).get('uv_index', [])
        current_uv_index = "N/A"
        for i, time_str in enumerate(uv_index_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_uv_index = uv_index_values[i]
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for UV Index.")
                continue
        data_points.append({
            "label": "UV-index", "measurement": current_uv_index, "unit": '',
            "is_uv": True,
            "uv_color": self.get_uv_color(current_uv_index),
            "uv_beams": self.get_uv_beam_points(current_uv_index)
        })

        # Visibility
        current_visibility = "N/A"
        visibility_hourly_times = hourly_data.get('time', [])
        visibility_values = hourly_data.get('visibility', [])
        if units == "imperial":
            visibility_conversion = 1/5280.     # ft to mi
            visibility_max = 6.2                # mi
        else:
            visibility_conversion = 0.001       # m to km
            visibility_max = 10.                # km
        for i, time_str in enumerate(visibility_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_visibility = visibility_values[i]*visibility_conversion
                    at_max_visibility = current_visibility >= visibility_max
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for visibility.")
                continue
        visibility_str = f"{current_visibility:.1f}"
        if at_max_visibility:
            visibility_str = u"\u2265" + visibility_str
        data_points.append({
            "label": "Zicht", 
            "measurement": visibility_str, 
            "unit": UNITS[units]["distance"],
            "icon": self.get_plugin_dir('icons/visibility.png')
        })

        # Air Quality
        aqi_hourly_times = aqi_data.get('hourly', {}).get('time', [])
        aqi_values = aqi_data.get('hourly', {}).get('european_aqi', [])
        current_aqi = "N/A"
        for i, time_str in enumerate(aqi_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_aqi = round(aqi_values[i], 1)
                    break
            except ValueError:
                logger.warning(f"Could not parse time string {time_str} for AQI.")
                continue
        scale = ""
        if current_aqi and current_aqi != "N/A":
            scale = ["Goed","Redelijk","Matig","Slecht","Zeer slecht","Extreem slecht"][min(current_aqi//20,5)]
        data_points.append({
            "label": "Luchtkwaliteit", "measurement": current_aqi,
            "unit": scale,
            "is_aqi": True,
            "aqi_rotation": self.get_european_aqi_rotation(current_aqi)
        })

        return data_points

    def get_wind_direction_abbr_nl(self, wind_deg: float) -> str:
        DIRECTIONS = ["N", "NO", "O", "ZO", "Z", "ZW", "W", "NW"]
        return DIRECTIONS[round(wind_deg / 45) % 8]

    def get_wind_icon_rotation(self, wind_deg: float) -> float:
        # wind_deg is the direction the wind is blowing FROM; the compass needle's
        # unrotated artwork points North (up), so add 180° to point where it's blowing to.
        return (wind_deg + 180) % 360

    def get_wind_speed_ms(self, speed: float, units: str) -> float:
        return speed * 0.44704 if units == "imperial" else speed

    def get_humidity_drop_count(self, humidity) -> int:
        try:
            humidity = float(humidity)
        except (TypeError, ValueError):
            return 1
        return min(5, max(1, math.ceil(humidity / 20)))

    def get_pressure_gauge_rotation(self, pressure) -> float:
        # Maps the typical 970-1050 hPa range onto a 180° needle sweep
        # (-90° to +90°), matching a flat-bottomed dome barometer face.
        try:
            pressure = float(pressure)
        except (TypeError, ValueError):
            pressure = 1013.25
        PRESSURE_MIN, PRESSURE_MAX = 970, 1050
        clamped = min(PRESSURE_MAX, max(PRESSURE_MIN, pressure))
        fraction = (clamped - PRESSURE_MIN) / (PRESSURE_MAX - PRESSURE_MIN)
        return -90 + fraction * 180

    def get_aqi_rotation_from_fraction(self, fraction_good: float) -> float:
        # fraction_good: 0 = worst (needle points left, into the red band), 1 = best (points right, into green).
        fraction_good = min(1.0, max(0.0, fraction_good))
        return -180 + (180 * fraction_good)

    def get_owm_aqi_rotation(self, aqi) -> float:
        # OWM scale is 1 (Good) - 5 (Very Poor).
        try:
            aqi = float(aqi)
        except (TypeError, ValueError):
            return self.get_aqi_rotation_from_fraction(0.5)
        return self.get_aqi_rotation_from_fraction((5 - aqi) / 4)

    def get_european_aqi_rotation(self, aqi) -> float:
        # European AQI: 0 (best) upwards, 100+ treated as worst.
        try:
            aqi = float(aqi)
        except (TypeError, ValueError):
            return self.get_aqi_rotation_from_fraction(0.5)
        return self.get_aqi_rotation_from_fraction(1 - min(aqi, 100) / 100)

    def get_uv_fraction(self, uv_index) -> float:
        try:
            uv_index = float(uv_index)
        except (TypeError, ValueError):
            uv_index = 0
        return min(1.0, max(0.0, uv_index / 11))

    def get_uv_color(self, uv_index) -> str:
        # Whitish yellow (low UV) fading to dark orange (high UV).
        LOW_COLOR, HIGH_COLOR = (255, 242, 178), (193, 68, 14)
        fraction = self.get_uv_fraction(uv_index)
        r, g, b = (round(low + (high - low) * fraction) for low, high in zip(LOW_COLOR, HIGH_COLOR))
        return f"#{r:02x}{g:02x}{b:02x}"

    def get_uv_beam_points(self, uv_index, beam_count=10, cx=60, cy=60, core_r=24, min_len=10, max_len=32, half_width=5):
        # Triangular sun beams whose length scales with UV index; fixed count keeps the sun silhouette recognizable.
        beam_len = min_len + (max_len - min_len) * self.get_uv_fraction(uv_index)
        outer_r = core_r + beam_len
        beams = []
        for i in range(beam_count):
            angle = (2 * math.pi * i / beam_count) - (math.pi / 2)
            perp = angle + (math.pi / 2)
            base_x, base_y = cx + core_r * math.cos(angle), cy + core_r * math.sin(angle)
            left = (base_x + half_width * math.cos(perp), base_y + half_width * math.sin(perp))
            right = (base_x - half_width * math.cos(perp), base_y - half_width * math.sin(perp))
            tip = (cx + outer_r * math.cos(angle), cy + outer_r * math.sin(angle))
            beams.append(f"{left[0]:.1f},{left[1]:.1f} {tip[0]:.1f},{tip[1]:.1f} {right[0]:.1f},{right[1]:.1f}")
        return beams

    def get_beaufort_description_nl(self, speed_ms: float) -> str:
        BEAUFORT_LEVELS = [
            (0.3, "Windstil"),
            (1.6, "Zwakke wind"),
            (3.4, "Zwakke wind"),
            (5.5, "Matige wind"),
            (8.0, "Matige wind"),
            (10.8, "Vrij krachtige wind"),
            (13.9, "Krachtige wind"),
            (17.2, "Harde wind"),
            (20.8, "Stormachtig"),
            (24.5, "Storm"),
            (28.5, "Zware storm"),
            (32.7, "Zeer zware storm"),
        ]
        for upper_bound, description in BEAUFORT_LEVELS:
            if speed_ms < upper_bound:
                return description
        return "Orkaan"

    def get_weather_data(self, api_key, units, lat, long):
        url = WEATHER_URL.format(lat=lat, long=long, units=units, api_key=api_key)
        response = requests.get(url, timeout=30)
        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to retrieve weather data: {response.content}")
            raise RuntimeError("Failed to retrieve weather data.")

        return response.json()

    def get_air_quality(self, api_key, lat, long):
        url = AIR_QUALITY_URL.format(lat=lat, long=long, api_key=api_key)
        response = requests.get(url, timeout=30)

        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to get air quality data: {response.content}")
            raise RuntimeError("Failed to retrieve air quality data.")

        return response.json()

    def get_location(self, api_key, lat, long):
        url = GEOCODING_URL.format(lat=lat, long=long, api_key=api_key)
        response = requests.get(url, timeout=30)

        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to get location: {response.content}")
            raise RuntimeError("Failed to retrieve location.")

        location_data = response.json()[0]
        location_str = f"{location_data.get('name')}, {location_data.get('state', location_data.get('country'))}"

        return location_str

    def get_nearest_location_name(self, lat, long):
        # Free reverse geocoding (no API key required), English place names via accept-language=en.
        try:
            response = requests.get(
                NOMINATIM_REVERSE_URL.format(lat=lat, long=long),
                headers={"User-Agent": "InkyPi-WeatherPlugin"},
                timeout=10
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
            logger.warning(f"Could not retrieve nearest location name: {str(e)}")
            return ""

    def get_open_meteo_data(self, lat, long, units, forecast_days):
        unit_params = OPEN_METEO_UNIT_PARAMS[units]
        url = OPEN_METEO_FORECAST_URL.format(lat=lat, long=long, forecast_days=forecast_days) + f"&{unit_params}"
        response = requests.get(url, timeout=30)

        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to retrieve Open-Meteo weather data: {response.content}")
            raise RuntimeError("Failed to retrieve Open-Meteo weather data.")
        
        return response.json()

    def get_open_meteo_air_quality(self, lat, long):
        url = OPEN_METEO_AIR_QUALITY_URL.format(lat=lat, long=long)
        response = requests.get(url, timeout=30)
        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to retrieve Open-Meteo air quality data: {response.content}")
            raise RuntimeError("Failed to retrieve Open-Meteo air quality data.")
        
        return response.json()
    
    def format_time(self, dt, time_format, hour_only=False, include_am_pm=True):
        """Format datetime based on 12h or 24h preference"""
        if time_format == "24h":
            return dt.strftime("%H:00" if hour_only else "%H:%M")
        
        if include_am_pm:
            fmt = "%I %p" if hour_only else "%I:%M %p"
        else:
            fmt = "%I" if hour_only else "%I:%M"

        return dt.strftime(fmt).lstrip("0")
    
    def parse_timezone(self, weatherdata):
        """Parse timezone from weather data"""
        if 'timezone' in weatherdata:
            logger.info(f"Using timezone from weather data: {weatherdata['timezone']}")
            return pytz.timezone(weatherdata['timezone'])
        else:
            logger.error("Failed to retrieve Timezone from weather data")
            raise RuntimeError("Timezone not found in weather data.")
