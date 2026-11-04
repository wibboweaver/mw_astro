"""Published OpenNGC angular dimensions; sizes are never inferred from previews."""
import csv
from functools import lru_cache
import math
import re

from catalogue import DATA_DIR


def normalise_id(identifier):
    compact = re.sub(r'\s+', '', identifier).upper()
    match = re.fullmatch(r'(NGC|IC|M)0*(\d+)(.*)', compact)
    return f'{match[1]}{int(match[2])}{match[3]}' if match else compact


def positive_number(value):
    try:
        value = float(value)
    except (ValueError, TypeError):
        return None
    return value if math.isfinite(value) and value > 0 else None


@lru_cache(maxsize=1)
def catalogue_sizes():
    """Map catalogue IDs and Messier aliases to (major, minor) in arcminutes."""
    sizes = {}
    for filename in ('NGC.csv', 'addendum.csv'):
        with (DATA_DIR / filename).open(encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle, delimiter=';'):
                major, minor = positive_number(row['MajAx']), positive_number(row['MinAx'])
                if major is None:
                    continue
                aliases = [row['Name']]
                if row['M'].strip():
                    aliases.append('M' + row['M'].strip())
                for alias in aliases:
                    sizes[normalise_id(alias)] = (major, minor)
    return sizes


def format_size(major_arcmin, minor_arcmin=None):
    """Use a shared unit for the published major and optional minor axes."""
    major = positive_number(major_arcmin)
    minor = positive_number(minor_arcmin)
    if major is None:
        return 'Unavailable'
    divisor, unit = (60, '°') if major >= 60 else (1, '′') if major >= 1 else (1/60, '″')
    def number(value):
        return f'{value/divisor:.2f}'.rstrip('0').rstrip('.')
    values = number(major) + (f' × {number(minor)}' if minor else '')
    return f'{values}{unit}'


def object_size_label(identifier):
    dimensions = catalogue_sizes().get(normalise_id(identifier))
    return format_size(*dimensions) if dimensions else 'Unavailable'


def frame_fit_label(identifier, camera_field):
    """Approximate major/minor-axis coverage, with the two long sides aligned."""
    dimensions = catalogue_sizes().get(normalise_id(identifier))
    if dimensions is None or camera_field is None:
        return '—'
    field = tuple(positive_number(value) for value in camera_field)
    if len(field) != 2 or None in field:
        return '—'
    long_side, short_side = sorted(field, reverse=True)
    major, minor = dimensions

    def coverage(size, side):
        if size is None:
            return '—'
        percent = size / (side * 60) * 100
        return '<1%' if percent < 1 else f'{percent:.0f}%'

    return f'{coverage(major, long_side)} × {coverage(minor, short_side)}'


from pathlib import Path
_loaded_source_stamp = Path(__file__).stat().st_mtime_ns


def frame_metrics(identifier, camera_field, camera_pixels=None, minimum_percent=15):
    """Approximate aligned major/minor footprints on the full, uncropped sensor."""
    dimensions=catalogue_sizes().get(normalise_id(identifier))
    if dimensions is None or camera_field is None or len(camera_field)!=2 or any(positive_number(v) is None for v in camera_field):
        return dict(coverage='—',pixels='—',status='Unknown',oversized=None)
    field=sorted(camera_field,reverse=True)
    coverage=[size/(side*60)*100 if size is not None else None for size,side in zip(dimensions,field)]
    pixels=[v*count/100 if v is not None else None for v,count in zip(coverage,sorted(camera_pixels,reverse=True))] if camera_pixels else [None,None]
    label=lambda values,unit:' × '.join('—' if v is None else (f'{v:.1f}%' if unit=='%' else f'{round(v):,}') for v in values)
    status='Unknown' if None in coverage else 'Pass' if max(coverage)>=minimum_percent else 'Fail'
    return dict(coverage=label(coverage,'%'),pixels=label(pixels,'px'),status=status,oversized=any(v is not None and v>100 for v in coverage))
