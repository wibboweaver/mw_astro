import numpy as np
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo

import pytest
from astronomical_night import night_for_chart,night_intervals,night_text,solar_altitudes


def test_normal_night_crossings_are_solar_minus_18_and_span_midnight():
    zone=ZoneInfo('Europe/London')
    start=datetime(2026,10,22,18,tzinfo=zone)
    periods=night_for_chart(start.date(),'Europe/London',start,start+timedelta(hours=12),52.293232,-3.036226,40)
    assert len(periods)==1
    night=periods[0]
    assert night.start_is_event and night.end_is_event
    assert night.start.astimezone(zone).date()==date(2026,10,22)
    assert night.end.astimezone(zone).date()==date(2026,10,23)
    for crossing in (night.start,night.end):
        assert float(solar_altitudes([crossing],52.293232,-3.036226,40)[0]) == pytest.approx(-18,abs=0.003)
    assert float(solar_altitudes([night.start+timedelta(hours=2)],52.293232,-3.036226,40)[0]) < -18
    text=night_text(periods,start.date(),'Europe/London')
    assert 'Start: 19:' in text and 'End: 05:' in text


def test_british_summer_without_astronomical_darkness():
    start=datetime(2026,6,21,18,tzinfo=ZoneInfo('Europe/London'))
    periods=night_for_chart(start.date(),'Europe/London',start,start+timedelta(hours=12),52.293232,-3.036226)
    assert periods==()
    assert night_text(periods,start.date(),'Europe/London')=='No astronomical night on this date.'


def test_continuous_polar_darkness_has_no_invented_crossings():
    start=datetime(2026,12,21,12,tzinfo=timezone.utc)
    periods=night_for_chart(start.date(),'UTC',start,start+timedelta(hours=12),89,0)
    assert len(periods)==1
    assert not periods[0].start_is_event and not periods[0].end_is_event
    assert 'no dusk/dawn crossing' in night_text(periods,start.date(),'UTC')


def test_long_chart_includes_both_nights():
    start=datetime(2026,10,22,18,tzinfo=ZoneInfo('Europe/London'))
    periods=night_for_chart(start.date(),'Europe/London',start,start+timedelta(hours=36),52.293232,-3.036226)
    assert len(periods)==2
    assert periods[0].end < periods[1].start


def test_chart_within_night_still_reports_true_dusk_and_dawn():
    start=datetime(2026,10,22,22,tzinfo=ZoneInfo('Europe/London'))
    periods=night_for_chart(start.date(),'Europe/London',start,start+timedelta(hours=1),52.293232,-3.036226)
    assert periods[0].start < start
    assert periods[0].end > start+timedelta(hours=1)


def test_dst_transition_preserves_real_event_instants():
    zone=ZoneInfo('Europe/London')
    start=datetime(2026,10,24,18,tzinfo=zone)
    night=night_for_chart(start.date(),'Europe/London',start,start+timedelta(hours=12),52.293232,-3.036226)[0]
    assert night.start.astimezone(zone).utcoffset()==timedelta(hours=1)
    assert night.end.astimezone(zone).utcoffset()==timedelta(0)
    wall_duration=night.end.astimezone(zone)-night.start.astimezone(zone)
    assert (night.end-night.start)-wall_duration==timedelta(hours=1)


def test_invalid_time_range():
    start=datetime(2026,10,22,tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        night_intervals(start,start,52,0)
    with pytest.raises(ValueError):
        night_intervals(start.replace(tzinfo=None),start,52,0)



def test_twilight_is_between_solar_thresholds_and_clipped(monkeypatch):
    import astronomical_night as module
    start=datetime(2026,11,4,16,tzinfo=timezone.utc)
    def fake_sun(times,*args):
        return np.array([-20+abs((t-start).total_seconds()/3600-2)*5 for t in times])
    monkeypatch.setattr(module,'solar_altitudes',fake_sun)
    periods=module.twilight_for_chart(start,start+timedelta(hours=4),52,-3)
    assert len(periods)==2
    for period in periods:
        assert start<=period.start<period.end<=start+timedelta(hours=4)
        assert -18<float(fake_sun([period.start+(period.end-period.start)/2])[0])<-12
        assert abs((period.end-period.start).total_seconds()-4320)<2
    middle=start+timedelta(hours=1)
    clipped=module.twilight_for_chart(middle,start+timedelta(hours=3),52,-3)
    assert clipped[0].start==middle
    monkeypatch.setattr(module,'solar_altitudes',lambda times,*args:np.full(len(times),-15.))
    assert len(module.twilight_for_chart(start,start+timedelta(hours=4),52,-3))==1
    monkeypatch.setattr(module,'solar_altitudes',lambda times,*args:np.full(len(times),-25.))
    assert not module.twilight_for_chart(start,start+timedelta(hours=4),52,-3)
