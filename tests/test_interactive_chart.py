import json
import pandas as pd
from interactive_chart import chart_html


def test_chart_has_local_time_continuous_readout_and_exact_time_range():
    frame = pd.DataFrame({"Time": pd.to_datetime(["2026-10-21T17:30Z", "2026-10-21T18:30Z"]), "Altitude (°)": [40, 50], "Azimuth (°)": [350, 10], "Horizon (°)": [10, 20]})
    html = chart_html(frame, 30, "Europe/London")
    data = json.loads(html.split('const data=')[1].split(';')[0])
    assert data["times"][0] == int(frame["Time"].iloc[0].timestamp()*1000)
    assert data["times"][-1] == int(frame["Time"].iloc[-1].timestamp()*1000)
    assert data["horizon"] == [10, 20]
    assert data["timezone"] == "Europe/London"
    assert "tip.textContent=timeFormat.format(selectedTime)" in html
    assert "svg.addEventListener('pointermove'" in html
    assert 'document.getElementById(\'alt\').textContent' in html


def test_time_only_readout_and_separate_catalogue_size_box():
    frame = pd.DataFrame({'Time': pd.to_datetime(['2026-10-21T17:00Z','2026-10-21T18:00Z']), 'Altitude (°)': [40,50], 'Azimuth (°)': [90,100]})
    html = chart_html(frame,40,'Europe/London','18 × 10 arcmin')
    data = json.loads(html.split('const data=')[1].split(';')[0])
    assert data['object_size'] == '18 × 10 arcmin'
    assert 'id="object-size"' in html
    assert 'Date/time' not in html and 'dateFormat' not in html
    assert "document.getElementById('datetime').textContent=timeFormat.format(selectedTime)" in html


def test_chart_exposes_two_click_interval_and_exposure_payload():
    frame = pd.DataFrame({'Time': pd.to_datetime(['2026-10-21T17:00Z','2026-10-21T18:00Z']), 'Altitude (°)': [40,50], 'Azimuth (°)': [90,100]})
    html = chart_html(frame,40,'Europe/London',exposure_seconds=240,target_key='fixture')
    data = json.loads(html.split('const data=')[1].split(';')[0])
    assert data['exposure_seconds'] == 240
    assert data['target_key'] == 'fixture'
    assert "svg.addEventListener('click'" in html
    assert 'id="duration"' in html and 'id="images"' in html
    assert 'sessionStorage.getItem(storageKey)' in html
    assert '__OBSERVATION_JS__' not in html


def test_astronomical_night_rectangle_is_behind_lines_and_clipped_to_plot():
    from datetime import datetime,timezone
    from astronomical_night import NightInterval
    frame=pd.DataFrame({'Time':pd.to_datetime(['2026-10-22T17:00Z','2026-10-23T05:00Z']),'Altitude (°)':[40,50],'Azimuth (°)':[90,100]})
    interval=NightInterval(datetime(2026,10,22,18,56,tzinfo=timezone.utc),datetime(2026,10,23,4,57,tzinfo=timezone.utc))
    html=chart_html(frame,40,'Europe/London',night_periods=(interval,))
    data=json.loads(html.split('const data=')[1].split(';')[0])
    assert data['astronomical_night']==[[int(interval.start.timestamp()*1000),int(interval.end.timestamp()*1000)]]
    assert html.index("'data-astronomical-night'") < html.index('for(let a=minY;')
    assert 'beginning=Math.max(t0,period[0]),ending=Math.min(t1,period[1])' in html
    assert "'pointer-events':'none'" in html



def test_selected_interval_missing_invalid_reversed_and_dst():
    from datetime import datetime, timezone
    import pytest
    from interactive_chart import selected_interval
    first=datetime(2026,10,24,23,tzinfo=timezone.utc)
    last=datetime(2026,10,25,5,tzinfo=timezone.utc)
    a,b=first.timestamp()*1000,last.timestamp()*1000
    for value, message in [({},'Missing start and stop'),({'interval':[a]},'Missing stop'),({'interval':[a,a]},'must be different'),({'interval':[a,b+1]},'outside'),({'interval':[float('nan')]},'outside')]:
        with pytest.raises(ValueError,match=message):selected_interval(value,first,last)
    assert selected_interval({'interval':[b,a]},first,last)==(first,last)
    assert (last-first).total_seconds()==6*3600


def test_moon_band_payload_and_layer_controls():
    times=pd.to_datetime(['2026-10-30T18:00Z','2026-10-31T06:00Z'])
    periods=[dict(start=times[0].timestamp()*1000,end=times[1].timestamp()*1000,level='possible')]
    frame=pd.DataFrame({'Time':times,'Altitude (°)':[40,50],'Azimuth (°)':[90,100]})
    html=chart_html(frame,40,'Europe/London',moon_intervals=periods)
    data=json.loads(html.split('const data=')[1].split(';')[0])
    assert data['moon_interference']==periods
    assert 'moon' not in data
    for name in ('horizon','object','minimum','moonlight'):
        assert f'id="show-{name}"' in html
    assert 'Moon trajectory' not in html
    assert "'data-moon-interference'" in html
    assert 'if(boundaries.length===1)renderInterval(selectedTime)' in html
