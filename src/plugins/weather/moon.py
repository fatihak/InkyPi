"""Moon illumination and moonrise/moonset, with no extra dependencies.

Uses the low-precision lunar and solar formulas from the Astronomical
Almanac (accurate to roughly 0.3 degrees), which put rise/set times within a
couple of minutes and illumination within about 1% - plenty for a display.
"""

import math
from datetime import datetime, timedelta, timezone

SYNODIC_MONTH = 29.530588853
_RAD = math.pi / 180


def _sin(d):
    return math.sin(d * _RAD)


def _cos(d):
    return math.cos(d * _RAD)


def _jd(dt):
    return dt.astimezone(timezone.utc).timestamp() / 86400.0 + 2440587.5


def _moon_ecliptic(T):
    """Geocentric ecliptic longitude, latitude and horizontal parallax (degrees)."""
    lon = (218.32 + 481267.881 * T
           + 6.29 * _sin(134.9 + 477198.85 * T) - 1.27 * _sin(259.2 - 413335.38 * T)
           + 0.66 * _sin(235.7 + 890534.23 * T) + 0.21 * _sin(269.9 + 954397.70 * T)
           - 0.19 * _sin(357.5 + 35999.05 * T) - 0.11 * _sin(186.6 + 966404.05 * T))
    lat = (5.13 * _sin(93.3 + 483202.03 * T) + 0.28 * _sin(228.2 + 960400.87 * T)
           - 0.28 * _sin(318.3 + 6003.18 * T) - 0.17 * _sin(217.6 - 407332.20 * T))
    par = (0.9508 + 0.0518 * _cos(134.9 + 477198.85 * T) + 0.0095 * _cos(259.2 - 413335.38 * T)
           + 0.0078 * _cos(235.7 + 890534.23 * T) + 0.0028 * _cos(269.9 + 954397.70 * T))
    return lon % 360, lat, par


def _sun_longitude(T):
    L0 = 280.46 + 36000.77 * T
    M = 357.53 + 35999.05 * T
    return (L0 + 1.915 * _sin(M) + 0.020 * _sin(2 * M)) % 360


def illumination(dt):
    """(percent illuminated 0-100, moon age in days 0-29.53, waxing?) at dt."""
    T = (_jd(dt) - 2451545.0) / 36525
    mlon, mlat, _ = _moon_ecliptic(T)
    slon = _sun_longitude(T)
    elong = (mlon - slon) % 360                    # 0 new, 180 full
    psi = math.degrees(math.acos(_cos(mlat) * _cos(mlon - slon)))  # true elongation
    pct = (1 - _cos(psi)) / 2 * 100                # phase angle ~ 180 - psi
    age = elong / 360 * SYNODIC_MONTH
    return pct, age, elong < 180


def _altitude(dt, lat, lon):
    """Geocentric moon altitude (deg) and horizontal parallax at dt."""
    jd = _jd(dt)
    T = (jd - 2451545.0) / 36525
    mlon, mlat, par = _moon_ecliptic(T)
    eps = 23.4393 - 0.0130 * T
    x = _cos(mlat) * _cos(mlon)
    y = _cos(eps) * _cos(mlat) * _sin(mlon) - _sin(eps) * _sin(mlat)
    z = _sin(eps) * _cos(mlat) * _sin(mlon) + _cos(eps) * _sin(mlat)
    ra = math.degrees(math.atan2(y, x))
    dec = math.degrees(math.asin(z))
    gmst = 280.46061837 + 360.98564736629 * (jd - 2451545.0)
    ha = gmst + lon - ra
    alt = math.degrees(math.asin(_sin(lat) * _sin(dec) + _cos(lat) * _cos(dec) * _cos(ha)))
    return alt, par


def _event_offset(dt, lat, lon):
    # Rise/set when the upper limb touches the horizon, allowing for parallax,
    # refraction (34') and semi-diameter: h0 = 0.7275 * parallax - 0.5667 deg.
    alt, par = _altitude(dt, lat, lon)
    return alt - (0.7275 * par - 0.5667)


def next_rise_set(now, lat, lon, hours=48):
    """Next moonrise and next moonset after `now` (aware datetime), in now's tz."""
    step = timedelta(minutes=10)
    t0, f0 = now, _event_offset(now, lat, lon)
    rise = set_ = None
    end = now + timedelta(hours=hours)
    while t0 < end and (rise is None or set_ is None):
        t1 = t0 + step
        f1 = _event_offset(t1, lat, lon)
        if (f0 < 0) != (f1 < 0):
            a, b, fa = t0, t1, f0
            for _ in range(20):                    # bisect to ~1 second
                m = a + (b - a) / 2
                fm = _event_offset(m, lat, lon)
                if (fa < 0) != (fm < 0):
                    b = m
                else:
                    a, fa = m, fm
            when = (a + (b - a) / 2).astimezone(now.tzinfo)
            if f0 < 0 and rise is None:
                rise = when
            elif f0 >= 0 and set_ is None:
                set_ = when
        t0, f0 = t1, f1
    return rise, set_
