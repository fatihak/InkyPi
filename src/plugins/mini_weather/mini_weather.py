import logging

import pytz
import requests
from datetime import datetime

from plugins.weather.weather import UNITS, Weather

logger = logging.getLogger(__name__)

REVERSE_GEOCODE_URL = (
    "https://nominatim.openstreetmap.org/reverse"
    "?lat={lat}&lon={long}&format=jsonv2&addressdetails=1&zoom=10"
)

LANGUAGE_LABELS = {
    "de": {
        "now": "JETZT",
        "days": ["MO", "DI", "MI", "DO", "FR", "SA", "SO"],
    },
    "en": {
        "now": "NOW",
        "days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"],
    },
    "es": {
        "now": "AHORA",
        "days": ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"],
    },
    "fr": {
        "now": "MAINT",
        "days": ["LUN", "MAR", "MER", "JEU", "VEN", "SAM", "DIM"],
    },
    "id": {
        "now": "SEK",
        "days": ["SEN", "SEL", "RAB", "KAM", "JUM", "SAB", "MIN"],
    },
    "it": {
        "now": "ORA",
        "days": ["LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM"],
    },
    "nl": {
        "now": "NU",
        "days": ["MA", "DI", "WO", "DO", "VR", "ZAT", "ZON"],
    },
    "pt": {
        "now": "AGORA",
        "days": ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"],
    },
}


def get_language_labels(language):
    return LANGUAGE_LABELS.get(language, LANGUAGE_LABELS["en"])


class MiniWeather(Weather):
    def generate_image(self, settings, device_config):
        lat_value = settings.get("latitude")
        long_value = settings.get("longitude")
        if lat_value in (None, "") or long_value in (None, ""):
            raise RuntimeError("Latitude and Longitude are required.")

        lat = float(lat_value)
        long = float(long_value)

        units = settings.get("units")
        if units not in UNITS:
            raise RuntimeError("Units are required.")

        language = str(settings.get("language", "en")).strip() or "en"
        weather_provider = settings.get("weatherProvider", "OpenMeteo")
        timezone_name = device_config.get_config("timezone", default="America/New_York")
        time_format = device_config.get_config("time_format", default="12h")
        local_tz = pytz.timezone(timezone_name)

        try:
            template_params, provider_tz, api_key = self._get_template_params(
                weather_provider,
                settings,
                units,
                lat,
                long,
                local_tz,
                time_format,
                device_config,
            )
            title = self._resolve_title(settings, weather_provider, lat, long, api_key)
        except Exception as exc:
            logger.error("%s request failed: %s", weather_provider, exc)
            raise RuntimeError(f"{weather_provider} request failure, please check logs.") from exc

        forecast = template_params.get("forecast", [])
        if not forecast:
            raise RuntimeError("Forecast data unavailable.")

        current_day = forecast[0]
        forecast_rows = forecast[1:5] if len(forecast) > 1 else forecast[:4]
        labels = get_language_labels(language)

        template_params.update(
            {
                "title": title,
                "current_label": labels["now"],
                "current_high": current_day["high"],
                "current_low": current_day["low"],
                "forecast_rows": self._localize_forecast_rows(forecast_rows, labels),
                "provider_timezone": provider_tz.zone,
                "plugin_settings": settings,
            }
        )

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        image = self.render_image(dimensions, "mini_weather.html", "mini_weather.css", template_params)
        if not image:
            raise RuntimeError("Failed to take screenshot, please check logs.")
        return image

    def _localize_forecast_rows(self, forecast_rows, labels):
        localized_rows = []
        for row in forecast_rows:
            row_copy = dict(row)
            weekday_index = row_copy.get("weekday_index")

            if isinstance(weekday_index, int):
                row_copy["day"] = labels["days"][weekday_index % 7]

            localized_rows.append(row_copy)

        return localized_rows

    def _get_template_params(
        self,
        weather_provider,
        settings,
        units,
        lat,
        long,
        local_tz,
        time_format,
        device_config,
    ):
        timezone_selection = settings.get("weatherTimeZone", "locationTimeZone")
        api_key = None

        if weather_provider == "OpenWeatherMap":
            api_key = device_config.load_env_key("OPEN_WEATHER_MAP_SECRET")
            if not api_key:
                raise RuntimeError("Open Weather Map API Key not configured.")

            weather_data = self.get_weather_data(api_key, units, lat, long)
            aqi_data = self.get_air_quality(api_key, lat, long)
            tz = self.parse_timezone(weather_data) if timezone_selection == "locationTimeZone" else local_tz
            template_params = self.parse_weather_data(weather_data, aqi_data, tz, units, time_format, lat)
            return template_params, tz, api_key

        if weather_provider == "OpenMeteo":
            weather_data = self.get_open_meteo_data(lat, long, units, 5)
            aqi_data = self.get_open_meteo_air_quality(lat, long)
            tz = self.parse_open_meteo_timezone(weather_data) if timezone_selection == "locationTimeZone" else local_tz
            template_params = self.parse_open_meteo_data(weather_data, aqi_data, tz, units, time_format, lat)
            return template_params, tz, api_key

        raise RuntimeError(f"Unknown weather provider: {weather_provider}")

    def _resolve_title(self, settings, weather_provider, lat, long, api_key):
        title_selection = settings.get("titleSelection", "location")
        custom_title = (settings.get("customTitle") or "").strip()

        if title_selection == "custom":
            if not custom_title:
                raise RuntimeError("Custom title is required.")
            return custom_title

        if weather_provider == "OpenWeatherMap":
            return self.get_location(api_key, lat, long)

        return self.get_reverse_geocoded_location(lat, long)

    def parse_open_meteo_timezone(self, weather_data):
        timezone_name = weather_data.get("timezone")
        if not timezone_name:
            raise RuntimeError("Timezone not found in weather data.")

        logger.info("Using timezone from Open-Meteo data: %s", timezone_name)
        return pytz.timezone(timezone_name)

    def get_reverse_geocoded_location(self, lat, long):
        headers = {"User-Agent": "InkyPi Mini Weather/1.0"}
        response = requests.get(
            REVERSE_GEOCODE_URL.format(lat=lat, long=long),
            headers=headers,
            timeout=30,
        )

        if not 200 <= response.status_code < 300:
            logger.warning("Failed to reverse geocode location: %s", response.content)
            return self.format_coordinates(lat, long)

        location_data = response.json()
        address = location_data.get("address", {})

        city = (
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("municipality")
            or address.get("county")
        )
        region = address.get("state") or address.get("country")

        if city and region:
            return f"{city}, {region}"
        if city:
            return city
        if region:
            return region

        display_name = location_data.get("display_name", "")
        if display_name:
            return ", ".join(display_name.split(", ")[:2])

        return self.format_coordinates(lat, long)

    def format_coordinates(self, lat, long):
        return f"{lat:.2f}, {long:.2f}"