"""Geometric ICRS target altitude calculations; no UI or network required."""
from datetime import datetime, timedelta, timezone

import numpy as np
import astropy.units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.time import Time
from astropy.utils import iers


def calculate_altitudes(ra_deg, dec_deg, latitude_deg, longitude_deg, height_m,
                        start: datetime, duration_hours=12, step_minutes=10, *, include_azimuth=False):
    """Return UTC timestamps and geometric altitudes in degrees.

    Set include_azimuth=True to also return azimuths (north=0°, east=90°).

    The bundled IERS table avoids network access. Atmospheric refraction is
    disabled; results are for planning, not precision pointing.
    """
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("start must include a timezone")
    values = [ra_deg, dec_deg, latitude_deg, longitude_deg, height_m, duration_hours, step_minutes]
    if not all(np.isfinite(value) for value in values):
        raise ValueError("All numeric inputs must be finite")
    if not -90 <= latitude_deg <= 90 or not -180 <= longitude_deg <= 180:
        raise ValueError("Invalid observing coordinates")
    if not -90 <= dec_deg <= 90:
        raise ValueError("Invalid declination")
    if not 0 < duration_hours <= 48 or not 1 <= step_minutes <= 60:
        raise ValueError("Invalid chart duration or sampling interval")
    minutes = np.arange(0, duration_hours * 60, step_minutes)
    minutes = np.append(minutes, duration_hours * 60)
    start_utc = start.astimezone(timezone.utc)
    timestamps = [start_utc + timedelta(minutes=float(value)) for value in minutes]
    location = EarthLocation.from_geodetic(longitude_deg * u.deg, latitude_deg * u.deg, height_m * u.m)
    target = SkyCoord(ra_deg * u.deg, dec_deg * u.deg, frame="icrs")
    with iers.conf.set_temp("auto_download", False):
        horizontal = target.transform_to(AltAz(obstime=Time(timestamps), location=location, pressure=0 * u.hPa))
    if include_azimuth:
        return timestamps, horizontal.alt.deg, horizontal.az.deg
    return timestamps, horizontal.alt.deg
