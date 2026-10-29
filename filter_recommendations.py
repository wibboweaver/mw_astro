"""Conservative DB2 recommendations from published OpenNGC object types."""
import csv
from functools import lru_cache
from catalogue import DATA_DIR
from object_sizes import normalise_id

# Emission-line classes appropriate for Ha/OIII imaging. Generic/mixed nebula
# classifications are deliberately left unclassified rather than guessed.
EMISSION_TYPES = {'EmN', 'HII', 'PN', 'SNR'}
BROADBAND_TYPES = {'G', 'GPair', 'GTrpl', 'GGroup', 'OCl', 'GCl', '*Ass', 'RfN', 'DrkN'}


@lru_cache(maxsize=1)
def catalogue_types():
    types = {}
    for filename in ('NGC.csv', 'addendum.csv'):
        with (DATA_DIR / filename).open(encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle, delimiter=';'):
                if row['Type'] in {'Dup', 'NonEx'}:
                    continue
                aliases = [row['Name']]
                if row['M'].strip():
                    aliases.append('M' + row['M'].strip())
                for alias in aliases:
                    types[normalise_id(alias)] = row['Type']
    return types


def recommend_db2(identifier):
    kind = catalogue_types().get(normalise_id(identifier))
    if kind in EMISSION_TYPES:
        return True, f'OpenNGC type {kind}: emission-line target; the ZWO DB2 2-inch Dual-Band Filter is recommended for Ha/OIII imaging.'
    if kind in BROADBAND_TYPES:
        return False, f'OpenNGC type {kind}: broadband target; the DB2 dual-band filter is not recommended for its main broadband structure.'
    return False, 'Object type is unknown or ambiguous: no automatic DB2 recommendation. An unticked box does not establish that a filter is unsuitable.'
