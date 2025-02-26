from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image
from jinja2 import Environment, FileSystemLoader, select_autoescape
import os
import requests
import logging
from datetime import datetime, timezone
import pytz
from io import BytesIO

logger = logging.getLogger(__name__)

WEATHER_URL = "https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={long}&units={units}&exclude=minutely&appid={api_key}"
AIR_QUALITY_URL = "http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={long}&appid={api_key}"

class Weather(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['api_key'] = {
            "required": True,
            "service": "OpenWeatherMap",
            "expected_key": "OPEN_WEATHER_MAP_SECRET"
        }
        return template_params

    def generate_image(self, settings, device_config):
        api_key = device_config.load_env_key("OPEN_WEATHER_MAP_SECRET")
        if not api_key:
            raise RuntimeError("Open Weather Map API Key not configured.")
        
        lat = settings.get('latitude')
        long = settings.get('longitude')
        if not lat or not long:
            raise RuntimeError("Latitude and Longitude are required.")
        
        units = settings.get('units')
        if not units or units not in ['metric', 'imperial', 'standard']:
            raise RuntimeError("Units are required.")

        weather_data = self.get_weather_data(api_key, units, lat, long)
        aqi_data = self.get_air_quality(api_key, lat, long)

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        
        image = Image.new("RGBA", dimensions, "white")

        timezone = device_config.get_config("timezone", default="America/New_York")
        tz = pytz.timezone(timezone)
        template_params = self.parse_weather_data(weather_data, aqi_data, tz, units)

        template_params["plugin_settings"] = settings

        image = self.render_image(dimensions, "weather.html", template_params)
        return image
    
    def parse_weather_data(self, weather_data, aqi_data, tz, units):
        data = {
            "current_date": "Friday, February 21",
            "current_day_icon": f"{self.get_plugin_dir('icons/sun.png')}",
            "current_temperature": "76°",
            "feels_like": "82°"
        }
        data['forecast'] = self.parse_forecast(weather_data.get('daily'), tz)
        data['data_points'] = self.parse_data_points(weather_data, aqi_data, tz, units)
        return data

    def parse_forecast(self, daily_forecast, tz):
        forecast = []
        for day in daily_forecast[1:]:
            dt = datetime.fromtimestamp(day.get('dt'), tz=timezone.utc).astimezone(tz)
            day_forecast = {
                "day": dt.strftime("%a"),
                "high": int(day.get("temp", {}).get("max")),
                "low": int(day.get("temp", {}).get("min")),
                "icon": f"{self.get_plugin_dir('icons/sun.png')}",
            }
            forecast.append(day_forecast)
        return forecast
        
    def parse_data_points(self, weather, air_quality, tz, units):
        data_points = []

        sunrise_epoch = weather.get('current', {}).get("sunrise")
        sunrise_dt = datetime.fromtimestamp(sunrise_epoch, tz=timezone.utc).astimezone(tz)
        data_points.append({
            "label": "Sunrise",
            "measurement": sunrise_dt.strftime('%I:%M').lstrip("0"),
            "unit": sunrise_dt.strftime('%p'),
            "icon": f"{self.get_plugin_dir('icons/sun.png')}"
        })

        sunset_epoch = weather.get('current', {}).get("sunset")
        sunset_dt = datetime.fromtimestamp(sunset_epoch, tz=timezone.utc).astimezone(tz)
        data_points.append({
            "label": "Sunset",
            "measurement": sunset_dt.strftime('%I:%M').lstrip("0"),
            "unit": sunset_dt.strftime('%p'),
            "icon": f"{self.get_plugin_dir('icons/sun.png')}"
        })

        data_points.append({
            "label": "Wind",
            "measurement": weather.get('current', {}).get("wind_speed"),
            "unit": 'mph' if units == 'imperial' else 'm/s',
            "icon": f"{self.get_plugin_dir('icons/sun.png')}"
        })

        data_points.append({
            "label": "Humidity",
            "measurement": weather.get('current', {}).get("humidity"),
            "unit": '%',
            "icon": f"{self.get_plugin_dir('icons/sun.png')}"
        })

        data_points.append({
            "label": "Pressure",
            "measurement": weather.get('current', {}).get("pressure"),
            "unit": 'hPa',
            "icon": f"{self.get_plugin_dir('icons/sun.png')}"
        })

        data_points.append({
            "label": "UV Index",
            "measurement": weather.get('current', {}).get("uvi"),
            "unit": '',
            "icon": f"{self.get_plugin_dir('icons/sun.png')}"
        })

        data_points.append({
            "label": "Visibility",
            "measurement": weather.get('current', {}).get("visibility")/1000,
            "unit": 'km',
            "icon": f"{self.get_plugin_dir('icons/sun.png')}"
        })

        aqi = air_quality.get('list', [])[0].get("main", {}).get("aqi")
        data_points.append({
            "label": "Air Quality Index",
            "measurement": aqi,
            "unit": ["Good", "Fair", "Moderate", "Poor", "Very Poor"][int(aqi)+1],
            "icon": f"{self.get_plugin_dir('icons/sun.png')}"
        })

        return data_points

    def get_weather_data(self, api_key, units, lat, long):
        url = WEATHER_URL.format(lat=lat, long=long, units=units, api_key=api_key)
        response = requests.get(url)

        if not 200 <= response.status_code < 300:
            logging.error("Failed to retrieve weather data.")
            raise RuntimeError("Failed to retrieve weather data.")
        
        logging.info("Successfully retrieved weather data")
        return response.json()
    
    def get_air_quality(self, api_key, lat, long):
        url = AIR_QUALITY_URL.format(lat=lat, long=long, api_key=api_key)
        response = requests.get(url)

        if not 200 <= response.status_code < 300:
            logging.error("Failed to get air quality data.")
            raise RuntimeError("Failed to retrieve air quality data.")
        
        logging.info("Successfully retrieved air quality data")
        return response.json()
