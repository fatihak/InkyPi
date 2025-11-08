from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
import os
import requests
import logging
from datetime import datetime, timezone, timedelta
import pytz
import csv
import math

logger = logging.getLogger(__name__)

UNITS = {
    "standard": {
        "temperature": "K",
        "speed": "m/s"
    },
    "metric": {
        "temperature": "°C",
        "speed": "m/s"
    },
    "imperial": {
        "temperature": "°F",
        "speed": "mph"
    }
}

WEATHER_URL = "https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={long}&units={units}&exclude=minutely&appid={api_key}"
AIR_QUALITY_URL = "http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={long}&appid={api_key}"
GEOCODING_URL = "http://api.openweathermap.org/geo/1.0/reverse?lat={lat}&lon={long}&limit=1&appid={api_key}"

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={long}&hourly=temperature_2m,precipitation,precipitation_probability&daily=weathercode,temperature_2m_max,temperature_2m_min,sunrise,sunset&current_weather=true&timezone=auto&models=best_match&forecast_days=4"
OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={long}&hourly=european_aqi,uv_index&timezone=auto"
OPEN_METEO_UNIT_PARAMS = {
    "standard": "temperature_unit=kelvin&wind_speed_unit=ms&precipitation_unit=mm",
    "metric":   "temperature_unit=celsius&wind_speed_unit=ms&precipitation_unit=mm",
    "imperial": "temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
}

class WeatherDashboard(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": False,
            "service": "OpenWeatherMap (Optional - uses Open-Meteo if not provided)",
            "expected_key": "OPEN_WEATHER_MAP_SECRET"
        }
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        lat = settings.get('latitude')
        long = settings.get('longitude')
        if not lat or not long:
            raise RuntimeError("Latitude and Longitude are required.")

        units = settings.get('units')
        if not units or units not in ['metric', 'imperial', 'standard']:
            raise RuntimeError("Units are required.")

        weather_provider = settings.get('weatherProvider', 'OpenMeteo')
        title = settings.get('customTitle', '')

        timezone = device_config.get_config("timezone", default="America/New_York")
        time_format = device_config.get_config("time_format", default="12h")
        tz = pytz.timezone(timezone)

        # Get weather data
        try:
            if weather_provider == "OpenWeatherMap":
                api_key = device_config.load_env_key("OPEN_WEATHER_MAP_SECRET")
                if not api_key:
                    raise RuntimeError("Open Weather Map API Key not configured.")
                weather_data = self.get_weather_data(api_key, units, lat, long)
                aqi_data = self.get_air_quality(api_key, lat, long)
                if settings.get('titleSelection', 'location') == 'location':
                    title = self.get_location(api_key, lat, long)
                template_params = self.parse_weather_data(weather_data, aqi_data, tz, units, time_format)
            elif weather_provider == "OpenMeteo":
                weather_data = self.get_open_meteo_data(lat, long, units)
                aqi_data = self.get_open_meteo_air_quality(lat, long)
                template_params = self.parse_open_meteo_data(weather_data, aqi_data, tz, units, time_format)
            else:
                raise RuntimeError(f"Unknown weather provider: {weather_provider}")

            template_params['title'] = title
        except Exception as e:
            logger.error(f"{weather_provider} request failed: {str(e)}")
            raise RuntimeError(f"{weather_provider} request failure, please check logs.")

        # Get birthdays from CSV
        csv_path = settings.get('birthdayCSVPath', '')
        birthdays = []
        if csv_path:
            # Expand tilde and environment variables
            csv_path = os.path.expanduser(csv_path)
            csv_path = os.path.expandvars(csv_path)
            logger.info(f"Looking for birthday CSV at: {csv_path}")
            if os.path.exists(csv_path):
                logger.info(f"Birthday CSV file found, loading birthdays...")
                birthdays = self.load_birthdays(csv_path, tz)
                logger.info(f"Loaded {len(birthdays)} upcoming birthdays")
            else:
                logger.warning(f"Birthday CSV file not found at: {csv_path}")

        # Get countdown info
        countdown_date_str = settings.get('countdownDate')
        countdown_title = settings.get('countdownTitle', 'Event')
        countdown_info = None
        if countdown_date_str:
            countdown_info = self.calculate_countdown(countdown_date_str, countdown_title, tz)

        # Get dimensions
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        # Add additional data
        template_params["plugin_settings"] = settings
        template_params["birthdays"] = birthdays
        template_params["countdown"] = countdown_info
        template_params["current_week"] = datetime.now(tz).isocalendar()[1]

        # Add countdown image if provided
        countdown_image = settings.get('countdownImage')
        if countdown_image and os.path.exists(countdown_image):
            template_params["countdown_image"] = countdown_image

        # Limit forecast to 3 days
        if 'forecast' in template_params:
            template_params['forecast'] = template_params['forecast'][:4]  # Current day + 3 forecast days

        # Add last refresh time
        now = datetime.now(tz)
        if time_format == "24h":
            last_refresh_time = now.strftime("%Y-%m-%d %H:%M")
        else:
            last_refresh_time = now.strftime("%Y-%m-%d %I:%M %p")
        template_params["last_refresh_time"] = last_refresh_time

        image = self.render_image(dimensions, "weather_dashboard.html", "weather_dashboard.css", template_params)

        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")
        return image

    def load_birthdays(self, csv_path, tz):
        """Load birthdays from CSV and return upcoming ones (within next 30 days)"""
        birthdays = []
        current_date = datetime.now(tz).date()
        current_year = current_date.year

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                # skipinitialspace removes spaces after commas
                reader = csv.DictReader(f, skipinitialspace=True)
                for row in reader:
                    try:
                        # Strip whitespace from keys and values to handle "name, date" headers
                        row = {k.strip(): v.strip() for k, v in row.items()}

                        # Parse birthday (expecting format: YYYY-MM-DD or MM-DD)
                        date_str = row.get('date', '').strip()
                        name = row.get('name', '').strip()

                        if not date_str or not name:
                            continue

                        birth_year = None
                        # Try parsing with year first
                        if len(date_str.split('-')) == 3:
                            birth_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                            birth_year = birth_date.year
                        else:
                            # Just month and day
                            birth_date = datetime.strptime(date_str, '%m-%d').date()
                            birth_date = birth_date.replace(year=current_year)

                        # Calculate next occurrence
                        next_birthday = birth_date.replace(year=current_year)
                        if next_birthday < current_date:
                            next_birthday = next_birthday.replace(year=current_year + 1)

                        # Only include if within next 30 days
                        days_until = (next_birthday - current_date).days
                        if days_until <= 30:
                            # Calculate age if birth year is known
                            age = None
                            if birth_year:
                                turning_age = next_birthday.year - birth_year
                                age = turning_age

                            birthday_entry = {
                                'name': name,
                                'date': next_birthday.strftime('%b %d'),
                                'days_until': days_until
                            }

                            if age:
                                birthday_entry['age'] = age

                            birthdays.append(birthday_entry)
                    except Exception as e:
                        logger.warning(f"Failed to parse birthday row: {row}, error: {e}")
                        continue

            # Sort by days until birthday
            birthdays.sort(key=lambda x: x['days_until'])

        except Exception as e:
            logger.error(f"Failed to load birthday CSV: {e}")

        return birthdays[:5]  # Limit to 5 upcoming birthdays

    def calculate_countdown(self, countdown_date_str, title, tz):
        """Calculate countdown information"""
        try:
            current_time = datetime.now(tz)
            countdown_date = datetime.strptime(countdown_date_str, "%Y-%m-%d")
            countdown_date = tz.localize(countdown_date)

            day_count = (countdown_date.date() - current_time.date()).days
            label = "Days Left" if day_count > 0 else "Days Passed"

            return {
                "title": title,
                "date": countdown_date.strftime("%B %d, %Y"),
                "day_count": abs(day_count),
                "label": label
            }
        except Exception as e:
            logger.error(f"Failed to calculate countdown: {e}")
            return None

    def parse_weather_data(self, weather_data, aqi_data, tz, units, time_format):
        """Parse OpenWeatherMap data"""
        current = weather_data.get("current")
        dt = datetime.fromtimestamp(current.get('dt'), tz=timezone.utc).astimezone(tz)
        current_icon = current.get("weather")[0].get("icon").replace("n", "d")

        # Get parent weather plugin directory for icons
        weather_plugin_dir = os.path.join(os.path.dirname(self.get_plugin_dir()), "weather")

        data = {
            "current_date": dt.strftime("%A, %B %d"),
            "current_day_icon": os.path.join(weather_plugin_dir, f'icons/{current_icon}.png'),
            "current_temperature": str(round(current.get("temp"))),
            "feels_like": str(round(current.get("feels_like"))),
            "current_description": current.get("weather")[0].get("description", "").title(),
            "temperature_unit": UNITS[units]["temperature"],
            "units": units,
            "time_format": time_format
        }

        data['forecast'] = self.parse_forecast(weather_data.get('daily'), tz, weather_plugin_dir)
        data['data_points'] = self.parse_compact_metrics(weather_data, aqi_data, tz, units, time_format, weather_plugin_dir)
        logger.info(f"Parsed data_points: {data['data_points']}")
        data['hourly_forecast'] = self.parse_hourly(weather_data.get('hourly'), tz, time_format, units)

        return data

    def parse_open_meteo_data(self, weather_data, aqi_data, tz, units, time_format):
        """Parse Open-Meteo data"""
        current = weather_data.get("current_weather", {})
        dt = datetime.fromisoformat(current.get('time')).astimezone(tz) if current.get('time') else datetime.now(tz)
        weather_code = current.get("weathercode", 0)
        current_icon = self.map_weather_code_to_icon(weather_code, dt.hour)

        # Get parent weather plugin directory for icons
        weather_plugin_dir = os.path.join(os.path.dirname(self.get_plugin_dir()), "weather")

        data = {
            "current_date": dt.strftime("%A, %B %d"),
            "current_day_icon": os.path.join(weather_plugin_dir, f'icons/{current_icon}.png'),
            "current_temperature": str(round(current.get("temperature", 0))),
            "feels_like": str(round(current.get("temperature", 0))),  # Open-Meteo doesn't provide feels_like in current
            "current_description": self.get_weather_description(weather_code),
            "temperature_unit": UNITS[units]["temperature"],
            "units": units,
            "time_format": time_format
        }

        data['forecast'] = self.parse_open_meteo_forecast(weather_data.get('daily', {}), tz, weather_plugin_dir)
        data['data_points'] = self.parse_open_meteo_compact_metrics(weather_data, aqi_data, tz, units, time_format, weather_plugin_dir)
        logger.info(f"Parsed data_points: {data['data_points']}")
        data['hourly_forecast'] = self.parse_open_meteo_hourly(weather_data.get('hourly', {}), tz, time_format)

        return data

    def parse_compact_metrics(self, weather, air_quality, tz, units, time_format, icon_dir):
        """Parse essential metrics only: Sunrise, Sunset, Wind, Humidity, UV, AQI (excludes Pressure & Visibility)"""
        data_points = []

        sunrise_epoch = weather.get('current', {}).get("sunrise")
        if sunrise_epoch:
            sunrise_dt = datetime.fromtimestamp(sunrise_epoch, tz=timezone.utc).astimezone(tz)
            data_points.append({
                "label": "Sunrise",
                "measurement": self.format_time(sunrise_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunrise_dt.strftime('%p'),
                "icon": os.path.join(icon_dir, 'icons/sunrise.png')
            })

        sunset_epoch = weather.get('current', {}).get("sunset")
        if sunset_epoch:
            sunset_dt = datetime.fromtimestamp(sunset_epoch, tz=timezone.utc).astimezone(tz)
            data_points.append({
                "label": "Sunset",
                "measurement": self.format_time(sunset_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunset_dt.strftime('%p'),
                "icon": os.path.join(icon_dir, 'icons/sunset.png')
            })

        data_points.append({
            "label": "Wind",
            "measurement": weather.get('current', {}).get("wind_speed"),
            "unit": UNITS[units]["speed"],
            "icon": os.path.join(icon_dir, 'icons/wind.png')
        })

        data_points.append({
            "label": "Humidity",
            "measurement": weather.get('current', {}).get("humidity"),
            "unit": '%',
            "icon": os.path.join(icon_dir, 'icons/humidity.png')
        })

        data_points.append({
            "label": "UV Index",
            "measurement": weather.get('current', {}).get("uvi"),
            "unit": '',
            "icon": os.path.join(icon_dir, 'icons/uvi.png')
        })

        aqi = air_quality.get('list', [])[0].get("main", {}).get("aqi") if air_quality.get('list') else None
        if aqi:
            data_points.append({
                "label": "Air Quality",
                "measurement": aqi,
                "unit": ["Good", "Fair", "Moderate", "Poor", "Very Poor"][int(aqi)-1],
                "icon": os.path.join(icon_dir, 'icons/aqi.png')
            })

        return data_points

    def parse_open_meteo_compact_metrics(self, weather_data, aqi_data, tz, units, time_format, icon_dir):
        """Parse essential metrics from Open-Meteo"""
        data_points = []
        daily_data = weather_data.get('daily', {})
        current_data = weather_data.get('current_weather', {})

        # Sunrise
        sunrise_times = daily_data.get('sunrise', [])
        if sunrise_times:
            sunrise_dt = datetime.fromisoformat(sunrise_times[0]).astimezone(tz)
            data_points.append({
                "label": "Sunrise",
                "measurement": self.format_time(sunrise_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunrise_dt.strftime('%p'),
                "icon": os.path.join(icon_dir, 'icons/sunrise.png')
            })

        # Sunset
        sunset_times = daily_data.get('sunset', [])
        if sunset_times:
            sunset_dt = datetime.fromisoformat(sunset_times[0]).astimezone(tz)
            data_points.append({
                "label": "Sunset",
                "measurement": self.format_time(sunset_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunset_dt.strftime('%p'),
                "icon": os.path.join(icon_dir, 'icons/sunset.png')
            })

        # Wind
        wind_speed = current_data.get("windspeed", 0)
        data_points.append({
            "label": "Wind",
            "measurement": wind_speed,
            "unit": UNITS[units]["speed"],
            "icon": os.path.join(icon_dir, 'icons/wind.png')
        })

        # Humidity - not available in Open-Meteo current_weather, skip or show N/A
        data_points.append({
            "label": "Humidity",
            "measurement": "N/A",
            "unit": '%',
            "icon": os.path.join(icon_dir, 'icons/humidity.png')
        })

        # UV Index
        current_time = datetime.now(tz)
        uv_hourly_times = aqi_data.get('hourly', {}).get('time', [])
        uv_values = aqi_data.get('hourly', {}).get('uv_index', [])
        current_uv = "N/A"
        for i, time_str in enumerate(uv_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    current_uv = uv_values[i]
                    break
            except Exception as e:
                logger.debug(f"Error parsing UV data: {e}")
                continue
        data_points.append({
            "label": "UV Index",
            "measurement": current_uv,
            "unit": '',
            "icon": os.path.join(icon_dir, 'icons/uvi.png')
        })

        # Air Quality
        aqi_hourly_times = aqi_data.get('hourly', {}).get('time', [])
        aqi_values = aqi_data.get('hourly', {}).get('european_aqi', [])
        current_aqi = "N/A"
        scale = ""
        for i, time_str in enumerate(aqi_hourly_times):
            try:
                if datetime.fromisoformat(time_str).astimezone(tz).hour == current_time.hour:
                    aqi_val = aqi_values[i]
                    current_aqi = aqi_val
                    if aqi_val is not None:
                        scale = ["Good","Fair","Moderate","Poor","Very Poor","Ext Poor"][min(int(aqi_val)//20, 5)]
                    break
            except Exception as e:
                logger.debug(f"Error parsing AQI data: {e}")
                continue
        data_points.append({
            "label": "Air Quality",
            "measurement": current_aqi,
            "unit": scale,
            "icon": os.path.join(icon_dir, 'icons/aqi.png')
        })

        return data_points

    def parse_forecast(self, daily_forecast, tz, icon_dir):
        """Parse forecast from OpenWeatherMap"""
        forecast = []
        for day in daily_forecast:
            weather_icon = day["weather"][0]["icon"].replace("n", "d")
            weather_icon_path = os.path.join(icon_dir, f"icons/{weather_icon}.png")
            dt = datetime.fromtimestamp(day["dt"], tz=timezone.utc).astimezone(tz)
            day_label = dt.strftime("%a")

            forecast.append({
                "day": day_label,
                "high": int(day["temp"]["max"]),
                "low": int(day["temp"]["min"]),
                "icon": weather_icon_path,
                "pop": int(day.get("pop", 0) * 100)  # Probability of precipitation
            })
        return forecast

    def parse_open_meteo_forecast(self, daily_data, tz, icon_dir):
        """Parse forecast from Open-Meteo"""
        times = daily_data.get('time', [])
        weather_codes = daily_data.get('weathercode', [])
        temp_max = daily_data.get('temperature_2m_max', [])
        temp_min = daily_data.get('temperature_2m_min', [])

        forecast = []
        for i in range(len(times)):
            dt = datetime.fromisoformat(times[i]).replace(tzinfo=timezone.utc).astimezone(tz)
            day_label = dt.strftime("%a")
            code = weather_codes[i] if i < len(weather_codes) else 0
            weather_icon = self.map_weather_code_to_icon(code, 12)
            weather_icon_path = os.path.join(icon_dir, f"icons/{weather_icon}.png")

            forecast.append({
                "day": day_label,
                "high": int(temp_max[i]) if i < len(temp_max) else 0,
                "low": int(temp_min[i]) if i < len(temp_min) else 0,
                "icon": weather_icon_path,
                "pop": 0  # Open-Meteo doesn't provide daily POP easily
            })
        return forecast

    def parse_hourly(self, hourly_forecast, tz, time_format, units):
        """Parse hourly forecast from OpenWeatherMap"""
        hourly = []
        for hour in hourly_forecast[:24]:
            dt = datetime.fromtimestamp(hour.get('dt'), tz=timezone.utc).astimezone(tz)
            rain_mm = hour.get("rain", {}).get("1h", 0.0)
            if units == "imperial":
                rain = rain_mm / 25.4
            else:
                rain = rain_mm
            hourly.append({
                "time": self.format_time(dt, time_format, hour_only=True),
                "temperature": int(hour.get("temp")),
                "precipitation": hour.get("pop"),
                "rain": round(rain, 2)
            })
        return hourly

    def parse_open_meteo_hourly(self, hourly_data, tz, time_format):
        """Parse hourly forecast from Open-Meteo"""
        hourly = []
        times = hourly_data.get('time', [])
        temperatures = hourly_data.get('temperature_2m', [])
        precipitation_probabilities = hourly_data.get('precipitation_probability', [])
        rain = hourly_data.get('precipitation', [])

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
            except:
                continue

        for i in range(start_index, min(start_index + 24, len(times))):
            dt = datetime.fromisoformat(times[i]).astimezone(tz)
            hourly.append({
                "time": self.format_time(dt, time_format, True),
                "temperature": int(temperatures[i]) if i < len(temperatures) else 0,
                "precipitation": (precipitation_probabilities[i] / 100) if i < len(precipitation_probabilities) else 0,
                "rain": rain[i] if i < len(rain) else 0
            })
        return hourly

    def map_weather_code_to_icon(self, weather_code, hour):
        """Map Open-Meteo weather codes to icon names"""
        icon = "01d"
        if weather_code in [0]: icon = "01d"
        elif weather_code in [1]: icon = "02d"
        elif weather_code in [2]: icon = "03d"
        elif weather_code in [3]: icon = "04d"
        elif weather_code in [45, 48]: icon = "50d"
        elif weather_code in [51, 53, 55, 56, 57]: icon = "09d"
        elif weather_code in [61, 63, 65, 66, 67]: icon = "10d"
        elif weather_code in [71, 73, 75, 77]: icon = "13d"
        elif weather_code in [80, 81, 82]: icon = "09d"
        elif weather_code in [85, 86]: icon = "13d"
        elif weather_code in [95, 96, 99]: icon = "11d"
        return icon

    def get_weather_description(self, weather_code):
        """Get human-readable weather description from code"""
        descriptions = {
            0: "Clear Sky", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
            45: "Foggy", 48: "Fog", 51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle",
            56: "Freezing Drizzle", 57: "Heavy Freezing Drizzle",
            61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
            66: "Freezing Rain", 67: "Heavy Freezing Rain",
            71: "Light Snow", 73: "Snow", 75: "Heavy Snow", 77: "Snow Grains",
            80: "Light Showers", 81: "Showers", 82: "Heavy Showers",
            85: "Light Snow Showers", 86: "Snow Showers",
            95: "Thunderstorm", 96: "Thunderstorm with Hail", 99: "Heavy Thunderstorm"
        }
        return descriptions.get(weather_code, "Unknown")

    def format_time(self, dt, time_format, hour_only=False, include_am_pm=True):
        """Format datetime based on 12h or 24h preference"""
        if time_format == "24h":
            return dt.strftime("%H:00" if hour_only else "%H:%M")

        if include_am_pm:
            fmt = "%-I %p" if hour_only else "%-I:%M %p"
        else:
            fmt = "%-I" if hour_only else "%-I:%M"
        return dt.strftime(fmt).lstrip("0")

    def get_weather_data(self, api_key, units, lat, long):
        """Fetch weather from OpenWeatherMap"""
        url = WEATHER_URL.format(lat=lat, long=long, units=units, api_key=api_key)
        response = requests.get(url)
        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to retrieve weather data: {response.content}")
            raise RuntimeError("Failed to retrieve weather data.")
        return response.json()

    def get_air_quality(self, api_key, lat, long):
        """Fetch air quality from OpenWeatherMap"""
        url = AIR_QUALITY_URL.format(lat=lat, long=long, api_key=api_key)
        response = requests.get(url)
        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to get air quality data: {response.content}")
            raise RuntimeError("Failed to retrieve air quality data.")
        return response.json()

    def get_location(self, api_key, lat, long):
        """Get location name from coordinates"""
        url = GEOCODING_URL.format(lat=lat, long=long, api_key=api_key)
        response = requests.get(url)
        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to get location: {response.content}")
            raise RuntimeError("Failed to retrieve location.")
        location_data = response.json()[0]
        return f"{location_data.get('name')}, {location_data.get('state', location_data.get('country'))}"

    def get_open_meteo_data(self, lat, long, units):
        """Fetch weather from Open-Meteo"""
        unit_params = OPEN_METEO_UNIT_PARAMS[units]
        url = OPEN_METEO_FORECAST_URL.format(lat=lat, long=long) + f"&{unit_params}"
        response = requests.get(url)
        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to retrieve Open-Meteo weather data: {response.content}")
            raise RuntimeError("Failed to retrieve Open-Meteo weather data.")
        return response.json()

    def get_open_meteo_air_quality(self, lat, long):
        """Fetch air quality from Open-Meteo"""
        url = OPEN_METEO_AIR_QUALITY_URL.format(lat=lat, long=long)
        response = requests.get(url)
        if not 200 <= response.status_code < 300:
            logger.error(f"Failed to retrieve Open-Meteo air quality data: {response.content}")
            raise RuntimeError("Failed to retrieve Open-Meteo air quality data.")
        return response.json()
