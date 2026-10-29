"""Automatic discovery catalogue from the attributed, bundled OpenNGC snapshot."""
import csv
from pathlib import Path
from targets import Target

DATA_DIR = Path(__file__).with_name('data') / 'openngc'
DEEP_SKY_TYPES = {'*Ass', 'OCl', 'GCl', 'Cl+N', 'G', 'GPair', 'GTrpl', 'GGroup', 'PN', 'HII', 'DrkN', 'EmN', 'Neb', 'RfN', 'SNR'}


def sexagesimal(value, hours=False):
    parts = value.strip().lstrip('+-').split(':')
    if len(parts) != 3:
        raise ValueError(f'Invalid catalogue coordinate: {value}')
    degrees = float(parts[0]) + float(parts[1])/60 + float(parts[2])/3600
    return degrees * (-1 if value.startswith('-') else 1) * (15 if hours else 1)


def read_openngc(paths, named_only=True):
    targets = []
    for path in paths:
        with Path(path).open(encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle, delimiter=';'):
                if row['Type'] not in DEEP_SKY_TYPES or not row['RA'] or not row['Dec']:
                    continue
                common, messier = row['Common names'].strip(), row['M'].strip()
                if named_only and not (common or messier):
                    continue
                identifier = row['Name']
                display = common or (f'M {int(messier)}' if messier else identifier)
                # Published common names are not unique; the ID disambiguates them.
                if display != identifier:
                    display = f'{display} ({identifier})'
                targets.append(Target(display, identifier, sexagesimal(row['RA'], hours=True), sexagesimal(row['Dec'])))
    return tuple(sorted(targets, key=lambda t: t.common_name.casefold()))


def load_catalogue(named_only=True):
    return read_openngc([DATA_DIR/'NGC.csv', DATA_DIR/'addendum.csv'], named_only)
