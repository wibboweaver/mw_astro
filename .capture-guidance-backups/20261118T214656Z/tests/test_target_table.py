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


def test_window_column_position_and_values():
    target=Target('Custom target','CUSTOM',30,-10)
    table=target_table((target,),START,-3,'Europe/London',{'Custom target':2.5})
    assert list(table.columns)[4:8]==['Transit time','Frame coverage','Object pixels','Window']
    assert table.iloc[0]['Window']=='02° 30′'


def test_observing_window_combines_limits_and_darkness():
    import pandas as pd
    import numpy as np
    from datetime import timedelta
    from astronomical_night import NightInterval
    from target_table import observing_window_hours
    start=datetime(2026,10,30,20,tzinfo=timezone.utc)
    frame=pd.DataFrame({'Time':[start,start+timedelta(hours=4)],'Altitude (°)':[20,60],'Azimuth (°)':[0,180]})
    night=(NightInterval(start+timedelta(hours=1),start+timedelta(hours=3)),)
    # Altitude reaches 40 at hour 2; astronomical darkness ends at hour 3.
    assert observing_window_hours(frame,40,None,night)==pytest.approx(1)
    # A higher local horizon delays the usable period to hour 2.5.
    profile=np.array([[0,45],[180,45]])
    assert observing_window_hours(frame,40,profile,night)==pytest.approx(.5)
    assert observing_window_hours(frame,40,None,())==0


def test_window_sums_disconnected_periods_and_uses_utc_elapsed_time():
    import pandas as pd
    from datetime import timedelta
    from astronomical_night import NightInterval
    from target_table import observing_window_hours
    start=datetime(2026,10,25,0,tzinfo=timezone.utc)
    times=[start+timedelta(hours=h) for h in (0,1,2,3,4)]
    frame=pd.DataFrame({'Time':times,'Altitude (°)':[50,30,50,30,50],'Azimuth (°)':[0]*5})
    assert observing_window_hours(frame,40,None,(NightInterval(times[0],times[-1]),))==pytest.approx(2)


def test_frame_fit_uses_aligned_dimensions_and_handles_unknown_sizes(monkeypatch):
    import object_sizes
    monkeypatch.setattr(object_sizes, 'catalogue_sizes', lambda: {
        'NGC224': (177.8, 69.7), 'MAJOR': (60., None), 'TINY': (.01, .005)})
    assert object_sizes.frame_fit_label('MISSING', (2.45,1.64)) == '—'
    assert object_sizes.frame_fit_label('NGC0224', (2.45,1.64)) == '121% × 71%'
    assert object_sizes.frame_fit_label('NGC0224', (1.64,2.45)) == '121% × 71%'
    assert object_sizes.frame_fit_label('MAJOR', (2.,1.)) == '50% × —'
    assert object_sizes.frame_fit_label('TINY', (2.,1.)) == '<1% × <1%'
    assert object_sizes.frame_fit_label('NGC0224', (1.225,.82)) == '242% × 142%'
    assert object_sizes.frame_fit_label('NGC0224', (0,1)) == '—'


def test_filter_column_order_and_yes_no_values():
    targets=(Target('Ring','M57',283.4,33.0),Target('Andromeda','M31',10.7,41.3),Target('Unknown','CUSTOM',30,-10))
    table=target_table(targets,START,-3,'Europe/London')
    assert list(table.columns).index('Filter?')==list(table.columns).index('Window')+1
    assert list(table['Filter?'])==['yes','no','no']


@pytest.mark.parametrize('hours,label',[(None,'—'),(0,'00° 00′'),(1.25,'01° 15′'),(1.999,'02° 00′'),(24,'24° 00′')])
def test_window_labels_hours_and_minutes(hours,label):
    from target_table import window_label
    assert window_label(hours)==label



def test_rating_preserved_and_weather_columns_removed():
    target=Target('Test','CUSTOM',30,-10)
    table=target_table((target,),START,-3,'Europe/London',ratings={'Test':dict(score=73,cloud=35,rain=10,reason='Test')})
    columns=list(table.columns)
    assert 'Cloud cover' not in columns
    assert 'Rain risk' not in columns
    assert table.iloc[0]['Night rating']==73
