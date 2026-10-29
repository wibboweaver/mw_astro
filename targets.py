"""Validated user-supplied target catalogue; no built-in or invented targets."""
import csv
from dataclasses import dataclass
import io
import math

MAX_TARGETS = 100


@dataclass(frozen=True)
class Target:
    common_name: str
    object_id: str
    ra_deg: float | None = None
    dec_deg: float | None = None


def parse_targets(text):
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if not {'common_name', 'object_id'} <= set(reader.fieldnames or []):
        raise ValueError('CSV needs common_name and object_id columns.')
    targets, names = [], set()
    for line, row in enumerate(reader, 2):
        if None in row:
            raise ValueError(f'Line {line}: too many CSV fields.')
        name, identifier = (row.get('common_name') or '').strip(), (row.get('object_id') or '').strip()
        if not name or not identifier:
            raise ValueError(f'Line {line}: common_name and object_id are required.')
        if name.casefold() in names:
            raise ValueError(f'Line {line}: duplicate common name {name}.')
        names.add(name.casefold())
        ra, dec = (row.get('ra_deg') or '').strip(), (row.get('dec_deg') or '').strip()
        if bool(ra) != bool(dec):
            raise ValueError(f'Line {line}: supply both ra_deg and dec_deg, or neither.')
        if ra:
            try:
                ra, dec = float(ra), float(dec)
            except ValueError as exc:
                raise ValueError(f'Line {line}: coordinates must be numeric.') from exc
            if not math.isfinite(ra) or not math.isfinite(dec) or not 0 <= ra < 360 or not -90 <= dec <= 90:
                raise ValueError(f'Line {line}: invalid ICRS coordinates in degrees.')
        else:
            ra = dec = None
        targets.append(Target(name, identifier, ra, dec))
        if len(targets) > MAX_TARGETS:
            raise ValueError(f'Catalogue is limited to {MAX_TARGETS} targets; none were loaded.')
    return tuple(targets)


def resolve_targets(targets, resolver):
    """Resolve missing coordinates only, preserving user-supplied common names."""
    resolved, failures = [], []
    for target in targets:
        if target.ra_deg is not None:
            resolved.append(target)
            continue
        try:
            result = resolver(target.object_id)
            ra, dec = float(result['ra_deg']), float(result['dec_deg'])
            if not math.isfinite(ra) or not math.isfinite(dec) or not 0 <= ra < 360 or not -90 <= dec <= 90:
                raise ValueError('SIMBAD returned invalid coordinates')
            resolved.append(Target(target.common_name, target.object_id, ra, dec))
        except Exception as exc:
            failures.append(f'{target.common_name} ({target.object_id}): {exc}')
    return tuple(resolved), tuple(failures)
