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
    divisor, unit = (60, '°') if major >= 60 else (1, 'arcmin') if major >= 1 else (1/60, 'arcsec')
    def number(value):
        return f'{value/divisor:.2f}'.rstrip('0').rstrip('.')
    values = number(major) + (f' × {number(minor)}' if minor else '')
    return f'{values}{unit}' if unit == '°' else f'{values} {unit}'


def object_size_label(identifier):
    dimensions = catalogue_sizes().get(normalise_id(identifier))
    return format_size(*dimensions) if dimensions else 'Unavailable'
