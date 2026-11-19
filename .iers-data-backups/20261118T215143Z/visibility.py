"""Batch target tracks and simultaneous altitude/horizon visibility filtering."""
from datetime import timedelta, timezone
import numpy as np
import pandas as pd
import astropy.units as u
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
from astropy.time import Time
from astropy.utils import iers
from horizon import horizon_altitudes

MODES = ('During window', 'At start', 'Throughout window')


def calculate_tracks(targets, latitude, longitude, height, start, duration_hours, step_minutes):
    if not targets:
        return {}
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError('Start must include a timezone.')
    if not 0 < duration_hours <= 48 or not 1 <= step_minutes <= 60:
        raise ValueError('Invalid window or sample interval.')
    offsets = np.append(np.arange(0, duration_hours * 60, step_minutes), duration_hours * 60)
    times = [start.astimezone(timezone.utc) + timedelta(minutes=float(m)) for m in offsets]
    coords = SkyCoord(np.array([t.ra_deg for t in targets])[:, None] * u.deg,
                      np.array([t.dec_deg for t in targets])[:, None] * u.deg, frame='icrs')
    site = EarthLocation.from_geodetic(longitude * u.deg, latitude * u.deg, height * u.m)
    with iers.conf.set_temp('auto_download', False):
        horizontal = coords.transform_to(AltAz(obstime=Time(times)[None, :], location=site, pressure=0 * u.hPa))
    return {t.common_name: pd.DataFrame({'Time': times, 'Altitude (°)': horizontal.alt.deg[i],
                                       'Azimuth (°)': horizontal.az.deg[i]}) for i, t in enumerate(targets)}


def visible_mask(frame, minimum_altitude, profile=None):
    altitudes = frame['Altitude (°)'].to_numpy()
    azimuths = frame['Azimuth (°)'].to_numpy()
    # Equality meets the user minimum; touching the obstruction is not clear.
    horizon = horizon_altitudes(profile, azimuths) if profile is not None else np.zeros(len(frame))
    return np.isfinite(altitudes) & np.isfinite(azimuths) & (altitudes >= minimum_altitude) & (altitudes > horizon)


def filter_tracks(tracks, minimum_altitude, profile=None, mode='During window'):
    if mode not in MODES:
        raise ValueError('Unknown visibility mode.')
    eligible = []
    for name, frame in tracks.items():
        mask = visible_mask(frame, minimum_altitude, profile)
        if not len(mask):
            continue
        qualifies = mask[0] if mode == 'At start' else mask.all() if mode == 'Throughout window' else mask.any()
        if qualifies:
            eligible.append(name)
    return eligible


def rank_tracks(tracks, minimum_altitude, profile=None, mode='During window', limit=100):
    """Keep the best qualifying tracks: most clear samples, then highest peak."""
    eligible = filter_tracks(tracks, minimum_altitude, profile, mode)
    return sorted(eligible, key=lambda name: (
        -int(visible_mask(tracks[name], minimum_altitude, profile).sum()),
        -float(tracks[name]['Altitude (°)'].max()), name.casefold(),
    ))[:limit]


def discover_tracks(targets, latitude, longitude, height, start, duration_hours,
                    step_minutes, minimum_altitude, profile=None, mode='During window', limit=100):
    """Search the full pool before limiting results; bound batch memory usage."""
    best = {}
    for offset in range(0, len(targets), 256):
        batch = calculate_tracks(targets[offset:offset+256], latitude, longitude, height,
                                 start, duration_hours, step_minutes)
        best.update(batch)
        names = rank_tracks(best, minimum_altitude, profile, mode, limit)
        best = {name: best[name] for name in names}
    return best
