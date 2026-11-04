"""Catalogue details and next upper meridian transits for the visible list."""
import csv
from functools import lru_cache
from datetime import timedelta, timezone as utc_timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import astropy.units as u
from astropy.coordinates import SkyCoord, TETE
from astropy.time import Time
from astropy.utils import iers

from catalogue import DATA_DIR
import filter_recommendations
from object_sizes import normalise_id, object_size_label, frame_metrics

TYPE_NAMES = {
    '*Ass': 'Stellar association', 'OCl': 'Open cluster', 'GCl': 'Globular cluster',
    'Cl+N': 'Cluster with nebulosity', 'G': 'Galaxy', 'GPair': 'Galaxy pair',
    'GTrpl': 'Galaxy triplet', 'GGroup': 'Galaxy group', 'PN': 'Planetary nebula',
    'HII': 'H II region', 'DrkN': 'Dark nebula', 'EmN': 'Emission nebula',
    'Neb': 'Nebula', 'RfN': 'Reflection nebula', 'SNR': 'Supernova remnant',
}


@lru_cache(maxsize=1)
def catalogue_details():
    details = {}
    for filename in ('NGC.csv', 'addendum.csv'):
        with (DATA_DIR / filename).open(encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle, delimiter=';'):
                detail = (row['Common names'].strip(), TYPE_NAMES.get(row['Type'], row['Type'] or 'Unavailable'))
                for alias in [row['Name'], *(['M' + row['M']] if row['M'].strip() else [])]:
                    details[normalise_id(alias)] = detail
    return details


def next_transits(targets, start, longitude):
    """Next upper transit at/after start, using apparent RA and sidereal time.

    All targets are solved together; no remote queries or track-sampling errors.
    """
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError('Start must include a timezone.')
    if not targets:
        return []
    coords = SkyCoord([t.ra_deg for t in targets] * u.deg,
                      [t.dec_deg for t in targets] * u.deg, frame='icrs')
    sidereal_day = 86164.0905
    with iers.conf.set_temp('auto_download', False):
        epoch = Time(start)
        ra = coords.transform_to(TETE(obstime=epoch)).ra.deg
        lst = epoch.sidereal_time('apparent', longitude=longitude * u.deg).deg
        offsets = np.mod(ra - lst, 360) / 360 * sidereal_day
        for _ in range(4):
            epochs = epoch + offsets * u.s
            ra = coords.transform_to(TETE(obstime=epochs)).ra.deg
            lst = epochs.sidereal_time('apparent', longitude=longitude * u.deg).deg
            residual = (ra - lst + 180) % 360 - 180
            offsets += residual / 360 * sidereal_day
        offsets = np.where(offsets < -0.01, offsets + sidereal_day, np.maximum(offsets, 0))
    return [(start.astimezone(utc_timezone.utc) + timedelta(seconds=float(value))).astimezone(start.tzinfo)
            for value in offsets]


def window_label(hours):
    if hours is None:
        return '—'
    minutes = int(float(hours) * 60 + 0.5)
    return f'{minutes // 60:02d}° {minutes % 60:02d}′'


def target_table(targets, start, longitude, timezone, windows=None, camera_field=None, camera_pixels=None, ratings=None):
    transits = next_transits(targets, start, longitude)
    rows = []
    for target, transit in zip(targets, transits):
        common, classification = catalogue_details().get(normalise_id(target.object_id), ('', 'Unavailable'))
        coordinate = SkyCoord(target.ra_deg * u.deg, target.dec_deg * u.deg)
        footprint=frame_metrics(target.object_id,camera_field,camera_pixels)
        rows.append({
            'Catalogue ID': target.object_id,
            'Common name': common or target.common_name.removesuffix(f' ({target.object_id})'),
            'Night rating': (ratings or {}).get(target.common_name,{}).get('score'),
            'Rating notes': (ratings or {}).get(target.common_name,{}).get('reason','Unknown'),
            'Transit time': transit.astimezone(ZoneInfo(timezone)).strftime('%H:%M'),
            'Frame coverage': footprint['coverage'],
            'Object pixels': footprint['pixels'],
            'Window': window_label(windows.get(target.common_name) if windows is not None else None),
            'Filter?': 'yes' if filter_recommendations.recommend_dualband(target.object_id)[0] else 'no',
            'Size': object_size_label(target.object_id),
            'Classification': classification,
            'Distance': 'Unavailable',
            'RA (J2000)': coordinate.ra.to_string(unit=u.hourangle, sep=':', precision=1, pad=True),
            'Dec (J2000)': coordinate.dec.to_string(unit=u.deg, sep=':', precision=0, pad=True, alwayssign=True),
        })
    return pd.DataFrame(rows)



def observing_window_hours(frame, minimum_altitude, profile, night_periods):
    """Total visible darkness in the chart range, interpolating sampled crossings."""
    from horizon import horizon_altitudes
    times=np.array([t.timestamp() for t in pd.to_datetime(frame['Time'],utc=True)])
    alt=frame['Altitude (°)'].to_numpy(dtype=float)
    az=frame['Azimuth (°)'].to_numpy(dtype=float)
    horizon=horizon_altitudes(profile,az) if profile is not None else np.zeros(len(alt))
    clearance=alt-horizon
    seconds=0.
    for i in range(len(times)-1):
        a,b=alt[i:i+2]-minimum_altitude
        c,d=clearance[i:i+2]
        if not np.isfinite([a,b,c,d,times[i],times[i+1]]).all() or times[i+1]<=times[i]:continue
        cuts={0.,1.}
        for first,last in ((a,b),(c,d)):
            if first!=last:
                crossing=-first/(last-first)
                if 0<crossing<1:cuts.add(float(crossing))
        cuts=sorted(cuts)
        for left,right in zip(cuts[:-1],cuts[1:]):
            mid=(left+right)/2
            if a+(b-a)*mid<0 or c+(d-c)*mid<=0:continue
            begin=times[i]+(times[i+1]-times[i])*left
            end=times[i]+(times[i+1]-times[i])*right
            for night in night_periods:
                seconds+=max(0.,min(end,night.end.timestamp())-max(begin,night.start.timestamp()))
    return seconds/3600


from pathlib import Path
_loaded_source_stamp = Path(__file__).stat().st_mtime_ns
