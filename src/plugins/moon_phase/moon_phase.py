from plugins.base_plugin.base_plugin import BasePlugin
from datetime import date
import math
import logging

logger = logging.getLogger(__name__)

LUNAR_CYCLE = 29.53058867
# Reference new moon: January 6, 2000
REFERENCE_NEW_MOON = date(2000, 1, 6)

PHASE_NAMES = [
    (0.03,  "New Moon"),
    (0.22,  "Waxing Crescent"),
    (0.28,  "First Quarter"),
    (0.47,  "Waxing Gibbous"),
    (0.53,  "Full Moon"),
    (0.72,  "Waning Gibbous"),
    (0.78,  "Last Quarter"),
    (0.97,  "Waning Crescent"),
    (1.00,  "New Moon"),
]


class MoonPhase(BasePlugin):

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        moon_data = self._compute_moon_data()

        lat = settings.get("latitude", "")
        lon = settings.get("longitude", "")
        tz  = settings.get("timezone", "UTC")

        moonrise_str, moonset_str = None, None
        if lat and lon:
            try:
                moonrise_str, moonset_str = self._compute_rise_set(
                    float(lat), float(lon), tz
                )
            except Exception as e:
                logger.warning("Could not compute moonrise/moonset: %s", e)

        template_params = {
            **moon_data,
            "moonrise": moonrise_str,
            "moonset": moonset_str,
            "plugin_settings": settings,
        }

        return self.render_image(dimensions, "moon_phase.html", "moon_phase.css", template_params)

    def _compute_rise_set(self, lat, lon, tz_name):
        from astral import LocationInfo
        from astral.moon import moonrise, moonset
        import pytz

        tz = pytz.timezone(tz_name)
        loc = LocationInfo(latitude=lat, longitude=lon, timezone=tz_name)
        today = date.today()

        rise = moonrise(loc.observer, today, tzinfo=tz)
        mset = moonset(loc.observer, today, tzinfo=tz)

        fmt = lambda dt: dt.strftime("%H:%M") if dt else None
        return fmt(rise), fmt(mset)

    def _compute_moon_data(self):
        today = date.today()
        days_since_ref = (today - REFERENCE_NEW_MOON).days
        phase_frac = (days_since_ref % LUNAR_CYCLE) / LUNAR_CYCLE

        phi = phase_frac * 2 * math.pi
        illumination = round((1 - math.cos(phi)) / 2 * 100)

        days_to_full = (0.5 - phase_frac) * LUNAR_CYCLE if phase_frac < 0.5 else (1.5 - phase_frac) * LUNAR_CYCLE
        days_to_new = (1.0 - phase_frac) * LUNAR_CYCLE

        phase_name = "New Moon"
        for threshold, name in PHASE_NAMES:
            if phase_frac <= threshold:
                phase_name = name
                break

        return {
            "phase_name": phase_name,
            "illumination": illumination,
            "days_to_full": round(days_to_full, 1),
            "days_to_new": round(days_to_new, 1),
            "svg_path": self._moon_svg_path(phase_frac),
            "is_waxing": phase_frac < 0.5,
        }

    def _moon_svg_path(self, phase_frac, r=80, cx=100, cy=100):
        phase = phase_frac % 1.0

        if phase < 0.01 or phase > 0.99:
            return ""  # New moon — no lit area

        if 0.49 < phase < 0.51:
            # Full moon — complete circle
            return f"M {cx - r} {cy} a {r} {r} 0 1 0 {2 * r} 0 a {r} {r} 0 1 0 -{2 * r} 0"

        phi = phase * 2 * math.pi
        term_rx = round(r * abs(math.cos(phi)), 2)
        top = f"{cx} {cy - r}"
        bot = f"{cx} {cy + r}"

        if phase < 0.5:
            # Waxing: right side lit
            outer = f"A {r} {r} 0 0 1 {bot}"
            if phase < 0.25:
                term = f"A {term_rx} {r} 0 0 0 {top}"
            else:
                term = f"A {term_rx} {r} 0 0 1 {top}"
        else:
            # Waning: left side lit
            outer = f"A {r} {r} 0 0 0 {bot}"
            if phase > 0.75:
                term = f"A {term_rx} {r} 0 0 1 {top}"
            else:
                term = f"A {term_rx} {r} 0 0 0 {top}"

        return f"M {top} {outer} {term}"
