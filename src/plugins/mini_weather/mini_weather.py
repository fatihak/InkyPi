import logging
import re
import unicodedata

import pytz
import requests
import datetime

from plugins.weather.weather import UNITS, Weather

logger = logging.getLogger(__name__)

REVERSE_GEOCODE_URL = (
    "https://nominatim.openstreetmap.org/reverse"
    "?lat={lat}&lon={long}&format=jsonv2&addressdetails=1&zoom=10"
)

QUICK_LOCATION_LABELS = {
    "52.3676,4.9041": "Amsterdam",
    "52.5200,13.4050": "Berlin",
    "-34.6037,-58.3816": "Buenos Aires",
    "-6.2088,106.8456": "Jakarta",
    "51.5074,-0.1278": "London",
    "40.4168,-3.7038": "Madrid",
    "40.7128,-74.0060": "New York",
    "48.8566,2.3522": "Paris",
    "-22.9068,-43.1729": "Rio de Janeiro",
    "41.9028,12.4964": "Rome",
    "-23.5505,-46.6333": "São Paulo",
    "35.6762,139.6503": "Tokyo",
}

QUICK_LOCATION_COORDS = {
    city: tuple(map(float, coords.split(",")))
    for coords, city in QUICK_LOCATION_LABELS.items()
}

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

# month names for a handful of supported languages; keep capitalized first letter
MONTH_NAMES = {
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
    "pt": [
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ],
    "es": [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ],
    "fr": [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ],
    "de": [
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ],
    "it": [
        "gennaio",
        "febbraio",
        "marzo",
        "aprile",
        "maggio",
        "giugno",
        "luglio",
        "agosto",
        "settembre",
        "ottobre",
        "novembre",
        "dicembre",
    ],
    "nl": [
        "januari",
        "februari",
        "maart",
        "april",
        "mei",
        "juni",
        "juli",
        "augustus",
        "september",
        "oktober",
        "november",
        "december",
    ],
    "id": [
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    ],
}


def format_localized_date(language, dt):
    """Return a short localized date string for the given language and datetime.

    Examples:
      en -> "March 25, 2026"
      pt -> "Março, 25 de 2026" (keeps month-first style as requested)
      fr/de/it/nl -> "25 mars 2026"
    """
    lang = (language or "").lower()
    months = MONTH_NAMES.get(lang, MONTH_NAMES.get("en"))
    raw_month = months[dt.month - 1]

    day = dt.day
    year = dt.year

    # Capitalization rules
    # - English: capitalize month (e.g., March)
    # - French: lowercase month (e.g., mars)
    # - Portuguese: keep month as provided in MONTH_NAMES (typically lowercase)
    if lang == "en" or lang.startswith("en-"):
        month = raw_month[0].upper() + raw_month[1:]
    elif lang == "fr" or lang.startswith("fr-"):
        month = raw_month.lower()
    else:
        month = raw_month

    # Formatting rules per language
    if lang == "en" or lang.startswith("en-"):
        # Month Day, Year -> March 25, 2026
        return f"{month} {day}, {year}"

    if lang == "fr" or lang.startswith("fr-"):
        # Day Month Year -> 25 mars 2026 (no commas/connectors)
        return f"{day} {month} {year}"

    if lang == "pt" or lang.startswith("pt-"):
        # Portuguese: Day de month de Year -> 25 de março de 2026
        return f"{day} de {month} de {year}"

    # Fallback: use English-style month-first formatting
    return f"{month} {day}, {year}"


def get_language_labels(language):
    return LANGUAGE_LABELS.get(language, LANGUAGE_LABELS["en"])


def is_valid_title(value):
    if value is None:
        return False

    title = str(value).strip()
    if len(title) < 2:
        return False

    # Require at least one letter/number to avoid titles like "," or "'".
    return bool(re.search(r"\w", title, flags=re.UNICODE))


def is_supported_title(value):
    if not is_valid_title(value):
        return False

    title = str(value).strip()
    has_letter = False

    for char in title:
        if not char.isalpha():
            continue

        has_letter = True
        if "LATIN" not in unicodedata.name(char, ""):
            return False

    return has_letter


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
        except Exception as exc:
            logger.error("%s request failed: %s", weather_provider, exc)
            raise RuntimeError(f"{weather_provider} request failure, please check logs.") from exc

        title = self._resolve_title_with_fallback(settings, weather_provider, lat, long, api_key)

        forecast = template_params.get("forecast", [])
        if not forecast:
            raise RuntimeError("Forecast data unavailable.")

        current_day = forecast[0]
        forecast_rows = forecast[1:5] if len(forecast) > 1 else forecast[:4]
        labels = get_language_labels(language)

        # localized date string
        now = datetime.datetime.now(local_tz)
        localized_date = format_localized_date(language, now)

        template_params.update(
            {
                "title": title,
                "current_label": labels["now"],
                "date": localized_date,
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

    def _resolve_title_with_fallback(self, settings, weather_provider, lat, long, api_key):
        try:
            title = self._resolve_title(settings, weather_provider, lat, long, api_key)
            if is_supported_title(title):
                return title
        except Exception as exc:
            logger.warning("Mini Weather title resolution failed, using fallback: %s", exc)

        quick_location = (settings.get("quickLocation") or "").strip()
        quick_location_label = QUICK_LOCATION_LABELS.get(quick_location)
        if quick_location_label:
            return quick_location_label

        matched_city = self._match_quick_location_by_coordinates(lat, long)
        if matched_city:
            return matched_city

        return self.format_coordinates(lat, long)

    def _match_quick_location_by_coordinates(self, lat, long, tolerance=0.02):
        for city, (city_lat, city_long) in QUICK_LOCATION_COORDS.items():
            if abs(lat - city_lat) <= tolerance and abs(long - city_long) <= tolerance:
                return city
        return None

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