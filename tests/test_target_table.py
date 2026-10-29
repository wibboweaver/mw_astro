from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import astropy.units as u
import pytest
from astropy.coordinates import SkyCoord, TETE
from astropy.time import Time
from astropy.utils import iers

from target_table import next_transits, target_table
from targets import Target

START = datetime(2026, 10, 22, 22, tzinfo=ZoneInfo('Europe/London'))


def test_metadata_alias_size_and_missing_distance():
    table = target_table((Target('Andromeda (NGC0224)', 'M31', 10.6847, 41.269),
                          Target('Custom target', 'CUSTOM', 30, -10)), START, -3, 'Europe/London')
    assert list(table['Catalogue ID']) == ['M31', 'CUSTOM']
    assert 'Andromeda' in table.iloc[0]['Common name']
    assert table.iloc[0]['Classification'] == 'Galaxy'
    assert '°' in table.iloc[0]['Size']
    assert list(table['Distance']) == ['Unavailable', 'Unavailable']
    assert table.iloc[1]['Classification'] == 'Unavailable'
    assert table.iloc[1]['Size'] == 'Unavailable'
    assert table.iloc[1]['Common name'] == 'Custom target'
    assert table.iloc[1]['RA (J2000)'] == '02:00:00.0'
    assert table.iloc[1]['Dec (J2000)'] == '-10:00:00'
    assert all(len(value) == 5 and value[2] == ':' for value in table['Transit time'])


def test_next_transits_are_upper_meridian_crossings_and_wrap_midnight():
    targets = (Target('A', 'A', 0, 40), Target('B', 'B', 180, -10), Target('C', 'C', 359.9, 80))
    transits = next_transits(targets, START, -3)
    assert all(0 <= (value - START).total_seconds() < 86165 for value in transits)
    assert any(value.date() > START.date() for value in transits)
    with iers.conf.set_temp('auto_download', False):
        for target, transit in zip(targets, transits):
            epoch = Time(transit)
            ra = SkyCoord(target.ra_deg*u.deg, target.dec_deg*u.deg).transform_to(TETE(obstime=epoch)).ra.deg
            lst = epoch.sidereal_time('apparent', longitude=-3*u.deg).deg
            assert abs((lst - ra + 180) % 360 - 180) < 0.00001


def test_same_instant_with_different_timezone_has_same_transit():
    targets = (Target('A', 'A', 10, 40),)
    local = next_transits(targets, START, 151)[0]
    utc = next_transits(targets, START.astimezone(timezone.utc), 151)[0]
    assert abs((local - utc).total_seconds()) < 0.01
    assert next_transits((), START, 0) == []
    with pytest.raises(ValueError, match='timezone'):
        next_transits(targets, START.replace(tzinfo=None), 0)


def test_transit_across_dst_matches_utc_solution():
    from datetime import timedelta
    start = datetime(2026, 10, 24, 23, tzinfo=ZoneInfo('Europe/London'))
    targets = (Target('A', 'A', 180, 40),)
    local = next_transits(targets, start, -3)[0]
    utc = next_transits(targets, start.astimezone(timezone.utc), -3)[0]
    assert abs((local.astimezone(timezone.utc) - utc).total_seconds()) < 0.01
    assert local.utcoffset() == timedelta(0)
