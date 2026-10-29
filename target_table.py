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
from object_sizes import normalise_id, object_size_label

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


def target_table(targets, start, longitude, timezone):
    transits = next_transits(targets, start, longitude)
    rows = []
    for target, transit in zip(targets, transits):
        common, classification = catalogue_details().get(normalise_id(target.object_id), ('', 'Unavailable'))
        coordinate = SkyCoord(target.ra_deg * u.deg, target.dec_deg * u.deg)
        rows.append({
            'Catalogue ID': target.object_id,
            'Common name': common or target.common_name.removesuffix(f' ({target.object_id})'),
            'Transit time': transit.astimezone(ZoneInfo(timezone)).strftime('%H:%M'),
            'Size': object_size_label(target.object_id),
            'Classification': classification,
            'Distance': 'Unavailable',
            'RA (J2000)': coordinate.ra.to_string(unit=u.hourangle, sep=':', precision=1, pad=True),
            'Dec (J2000)': coordinate.dec.to_string(unit=u.deg, sep=':', precision=0, pad=True, alwayssign=True),
        })
    return pd.DataFrame(rows)
