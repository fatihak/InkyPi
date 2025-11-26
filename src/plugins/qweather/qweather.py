from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
import os
import requests
import logging
from datetime import datetime, timezone, date
from astral import moon
import pytz
from io import BytesIO
import math

logger = logging.getLogger(__name__)

def get_moon_phase_name(phase_age: float) -> str:
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
    "metric": {
        "temperature": "°C",
        "speed": "km/h"
    },
    "imperial": {
        "temperature": "°F",
        "speed": "mph"
    }
}

QWEATHER_ICON_MAP = {
    "100": "01d",
    "101": "02d",
    "102": "02d",
    "103": "03d",
    "104": "04d",
    "150": "02d",
    "151": "02d",
    "152": "02d",
    "153": "03d",
    "154": "04d",
    "300": "09d",
    "301": "09d",
    "302": "10d",
    "303": "11d",
    "304": "11d",
    "305": "10d",
    "306": "10d",
    "307": "10d",
    "308": "10d",
    "309": "09d",
    "310": "10d",
    "311": "10d",
    "312": "10d",
    "313": "10d",
    "314": "09d",
    "315": "10d",
    "316": "10d",
    "317": "10d",
    "318": "10d",
    "350": "09d",
    "351": "09d",
    "399": "10d",
    "400": "13d",
    "401": "13d",
    "402": "13d",
    "403": "13d",
    "404": "13d",
    "405": "13d",
    "406": "13d",
    "407": "13d",
    "408": "13d",
    "409": "13d",
    "410": "13d",
    "456": "13d",
    "457": "13d",
    "499": "13d",
    "500": "50d",
    "501": "50d",
    "502": "50d",
    "503": "50d",
    "504": "50d",
    "507": "50d",
    "508": "50d",
    "509": "50d",
    "510": "50d",
    "511": "50d",
    "512": "50d",
    "513": "50d",
    "514": "50d",
    "515": "50d",
    "800": "01d",
    "801": "02d",
    "802": "03d",
    "803": "04d",
    "804": "04d",
    "805": "04d",
    "806": "04d",
    "807": "04d"
}

class QWeather(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "QWeather (和风天气)",
            "expected_key": "QWEATHER_API_KEY"
        }
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        lat = settings.get('latitude')
        long = settings.get('longitude')
        if not lat or not long:
            raise RuntimeError("Latitude and Longitude are required.")

        units = settings.get('units', 'metric')
        if units not in ['metric', 'imperial']:
            raise RuntimeError("Units must be metric or imperial.")

        api_key = device_config.load_env_key("QWEATHER_API_KEY")
        if not api_key:
            raise RuntimeError("QWeather API Key not configured.")

        host = settings.get('qweatherHost') or device_config.load_env_key("QWEATHER_HOST") or 'https://devapi.qweather.com'
        title = settings.get('customTitle', '')

        timezone = device_config.get_config("timezone", default="Asia/Shanghai")
        time_format = device_config.get_config("time_format", default="24h")
        tz = pytz.timezone(timezone)

        try:
            location_id = self.get_location_id(host, api_key, lat, long)

            weather_data = self.get_weather_data(host, api_key, location_id, units)
            daily_forecast = self.get_daily_forecast(host, api_key, location_id, units)
            hourly_forecast = self.get_hourly_forecast(host, api_key, location_id, units)
            air_quality = self.get_air_quality(host, api_key, location_id)

            if not title:
                title = weather_data.get('location_name', '')

            template_params = self.parse_weather_data(
                weather_data,
                daily_forecast,
                hourly_forecast,
                air_quality,
                tz,
                units,
                time_format
            )
            template_params['title'] = title

        except Exception as e:
            logger.error(f"QWeather request failed: {str(e)}")
            raise RuntimeError(f"QWeather request failure: {str(e)}")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        template_params["plugin_settings"] = settings

        now = datetime.now(tz)
        if time_format == "24h":
            last_refresh_time = now.strftime("%Y-%m-%d %H:%M")
        else:
            last_refresh_time = now.strftime("%Y-%m-%d %I:%M %p")
        template_params["last_refresh_time"] = last_refresh_time

        image = self.render_image(dimensions, "qweather.html", "qweather.css", template_params)

        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")
        return image

    def get_location_id(self, host, api_key, lat, long):
        return f"{lat},{long}"

    def get_weather_data(self, host, api_key, location_id, units):
        url = f"{host}/weather/v1/current/{location_id}"
        params = {
            "key": api_key,
            "unit": "m" if units == "metric" else "i"
        }
        response = requests.get(url, params=params)

        if response.status_code != 200:
            logger.error(f"Failed to retrieve weather data: {response.content}")
            raise RuntimeError("Failed to retrieve weather data.")

        data = response.json()
        if data.get('code') != '200':
            logger.error(f"Invalid weather response: {data}")
            raise RuntimeError("Failed to get valid weather data.")

        return data['now']

    def get_daily_forecast(self, host, api_key, location_id, units):
        url = f"{host}/weather/v1/daily/{location_id}"
        params = {
            "key": api_key,
            "unit": "m" if units == "metric" else "i",
            "days": 7
        }
        response = requests.get(url, params=params)

        if response.status_code != 200:
            logger.error(f"Failed to retrieve daily forecast: {response.content}")
            raise RuntimeError("Failed to retrieve daily forecast.")

        data = response.json()
        if data.get('code') != '200':
            logger.error(f"Invalid forecast response: {data}")
            raise RuntimeError("Failed to get valid forecast data.")

        return data['daily']

    def get_hourly_forecast(self, host, api_key, location_id, units):
        url = f"{host}/weather/v1/hourly/{location_id}"
        params = {
            "key": api_key,
            "unit": "m" if units == "metric" else "i",
            "hours": 24
        }
        response = requests.get(url, params=params)

        if response.status_code != 200:
            logger.error(f"Failed to retrieve hourly forecast: {response.content}")
            raise RuntimeError("Failed to retrieve hourly forecast.")

        data = response.json()
        if data.get('code') != '200':
            logger.error(f"Invalid hourly forecast response: {data}")
            raise RuntimeError("Failed to get valid hourly forecast data.")

        return data['hourly']

    def get_air_quality(self, host, api_key, location_id):
        url = f"{host}/airquality/v1/current/{location_id}"
        params = {
            "key": api_key
        }
        response = requests.get(url, params=params)

        if response.status_code != 200:
            logger.error(f"Failed to get air quality data: {response.content}")
            return {}

        data = response.json()
        if data.get('code') != '200':
            logger.error(f"Invalid air quality response: {data}")
            return {}

        return data.get('now', {})

    def parse_weather_data(self, weather_data, daily_forecast, hourly_forecast, air_quality, tz, units, time_format):
        current_icon = self.map_qweather_icon(weather_data.get('icon', '100'))
        current_temp = float(weather_data.get('temp', 0))
        feels_like = float(weather_data.get('feelsLike', current_temp))

        data = {
            "current_date": datetime.now(tz).strftime("%A, %B %d"),
            "current_day_icon": self.get_plugin_dir(f'icons/{current_icon}.png'),
            "current_temperature": str(round(current_temp)),
            "feels_like": str(round(feels_like)),
            "temperature_unit": UNITS[units]["temperature"],
            "units": units,
            "time_format": time_format
        }

        data['forecast'] = self.parse_forecast(daily_forecast, tz)
        data['data_points'] = self.parse_data_points(weather_data, daily_forecast[0] if daily_forecast else {}, air_quality, tz, units, time_format)
        data['hourly_forecast'] = self.parse_hourly(hourly_forecast, tz, time_format, units)

        return data

    def map_qweather_icon(self, qweather_icon):
        return QWEATHER_ICON_MAP.get(str(qweather_icon), "01d")

    def parse_forecast(self, daily_forecast, tz):
        forecast = []

        for day in daily_forecast:
            weather_icon = self.map_qweather_icon(day.get('iconDay', '100'))
            weather_icon_path = self.get_plugin_dir(f"icons/{weather_icon}.png")

            dt = datetime.fromisoformat(day['fxDate']).replace(tzinfo=tz)
            day_label = dt.strftime("%a")

            target_date = dt.date()
            try:
                phase_age = moon.phase(target_date)
                phase_name = get_moon_phase_name(phase_age)
                LUNAR_CYCLE_DAYS = 29.530588853
                phase_fraction = phase_age / LUNAR_CYCLE_DAYS
                illum_pct = (1 - math.cos(2 * math.pi * phase_fraction)) / 2 * 100
            except Exception as e:
                logger.error(f"Error calculating moon phase for {target_date}: {e}")
                illum_pct = 0
                phase_name = "newmoon"

            moon_icon_path = self.get_plugin_dir(f"icons/{phase_name}.png")

            forecast.append({
                "day": day_label,
                "high": int(float(day.get('tempMax', 0))),
                "low": int(float(day.get('tempMin', 0))),
                "icon": weather_icon_path,
                "moon_phase_pct": f"{illum_pct:.0f}",
                "moon_phase_icon": moon_icon_path,
            })

        return forecast

    def parse_hourly(self, hourly_forecast, tz, time_format, units):
        hourly = []
        current_time = datetime.now(tz)

        for hour in hourly_forecast[:24]:
            dt = datetime.fromisoformat(hour['fxTime']).replace(tzinfo=pytz.UTC).astimezone(tz)

            if dt < current_time:
                continue

            precip_prob = float(hour.get('pop', 0)) / 100.0
            precip_amount = float(hour.get('precip', 0))

            if units == "imperial":
                precip_amount = precip_amount / 25.4

            hour_forecast = {
                "time": self.format_time(dt, time_format, hour_only=True),
                "temperature": int(float(hour.get('temp', 0))),
                "precipitation": precip_prob,
                "rain": round(precip_amount, 2)
            }
            hourly.append(hour_forecast)

            if len(hourly) >= 24:
                break

        return hourly

    def parse_data_points(self, current_weather, today_forecast, air_quality, tz, units, time_format):
        data_points = []

        sunrise_str = today_forecast.get('sunrise')
        if sunrise_str:
            sunrise_dt = datetime.strptime(sunrise_str, "%H:%M").replace(
                year=datetime.now(tz).year,
                month=datetime.now(tz).month,
                day=datetime.now(tz).day,
                tzinfo=tz
            )
            data_points.append({
                "label": "Sunrise",
                "measurement": self.format_time(sunrise_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunrise_dt.strftime('%p'),
                "icon": self.get_plugin_dir('icons/sunrise.png')
            })

        sunset_str = today_forecast.get('sunset')
        if sunset_str:
            sunset_dt = datetime.strptime(sunset_str, "%H:%M").replace(
                year=datetime.now(tz).year,
                month=datetime.now(tz).month,
                day=datetime.now(tz).day,
                tzinfo=tz
            )
            data_points.append({
                "label": "Sunset",
                "measurement": self.format_time(sunset_dt, time_format, include_am_pm=False),
                "unit": "" if time_format == "24h" else sunset_dt.strftime('%p'),
                "icon": self.get_plugin_dir('icons/sunset.png')
            })

        wind_speed = current_weather.get('windSpeed', '0')
        data_points.append({
            "label": "Wind",
            "measurement": wind_speed,
            "unit": UNITS[units]["speed"],
            "icon": self.get_plugin_dir('icons/wind.png')
        })

        humidity = current_weather.get('humidity', '0')
        data_points.append({
            "label": "Humidity",
            "measurement": humidity,
            "unit": '%',
            "icon": self.get_plugin_dir('icons/humidity.png')
        })

        pressure = current_weather.get('pressure', '0')
        data_points.append({
            "label": "Pressure",
            "measurement": pressure,
            "unit": 'hPa',
            "icon": self.get_plugin_dir('icons/pressure.png')
        })

        uv_index = today_forecast.get('uvIndex', '0')
        data_points.append({
            "label": "UV Index",
            "measurement": uv_index,
            "unit": '',
            "icon": self.get_plugin_dir('icons/uvi.png')
        })

        visibility = float(current_weather.get('vis', '10'))
        visibility_str = f">{visibility}" if visibility >= 10 else visibility
        data_points.append({
            "label": "Visibility",
            "measurement": visibility_str,
            "unit": 'km',
            "icon": self.get_plugin_dir('icons/visibility.png')
        })

        if air_quality:
            aqi = air_quality.get('aqi', 'N/A')
            aqi_category = air_quality.get('category', '')
            data_points.append({
                "label": "Air Quality",
                "measurement": aqi,
                "unit": aqi_category,
                "icon": self.get_plugin_dir('icons/aqi.png')
            })

        return data_points

    def format_time(self, dt, time_format, hour_only=False, include_am_pm=True):
        if time_format == "24h":
            return dt.strftime("%H:00" if hour_only else "%H:%M")

        if include_am_pm:
            fmt = "%-I %p" if hour_only else "%-I:%M %p"
        else:
            fmt = "%-I" if hour_only else "%-I:%M"

        return dt.strftime(fmt).lstrip("0")
