from datetime import datetime,timezone,timedelta
from io import BytesIO
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import urlparse,parse_qs
import json
import pytest
from cloud_forecast import fetch_cloud_forecast,forecast_for_chart,load_cloud_settings,DEFAULTS


def response(values=(0,35,None,100)):
    return BytesIO(json.dumps(dict(hourly_units={'cloud_cover':'%'},hourly=dict(time=[1793318400+i*3600 for i in range(len(values))],cloud_cover=list(values)))).encode())


def test_fetch_validates_units_preserves_zero_and_missing():
    with patch('cloud_forecast.urlopen',return_value=response()) as call:
        data=fetch_cloud_forecast(52,-3)
        assert [b['percent'] for b in data['segments']]==[0,35,None,100]
        assert data['segments'][0]['end']-data['segments'][0]['start']==3600000
        query=parse_qs(urlparse(call.call_args.args[0]).query)
        assert query['timezone']==['UTC'] and query['timeformat']==['unixtime']
        assert query['hourly']==['cloud_cover']
        assert data['retrieved_at']


@pytest.mark.parametrize('value',[-1,101,True,'bad'])
def test_invalid_percentage(value):
    with patch('cloud_forecast.urlopen',return_value=response([value])):
        with pytest.raises(ValueError):fetch_cloud_forecast(52,-3)


def test_outside_range_does_not_request_and_failure_is_unknown():
    now=datetime(2026,10,30,tzinfo=timezone.utc)
    with patch('cloud_forecast.urlopen') as call:
        result=forecast_for_chart(now+timedelta(days=20),now+timedelta(days=21),52,-3,DEFAULTS,now=now)
        assert not result['segments'] and 'No forecast' in result['error']
        call.assert_not_called()
    with patch('cloud_forecast.urlopen',side_effect=URLError('offline')):
        result=forecast_for_chart(now,now+timedelta(hours=12),52,-3,DEFAULTS,now=now)
        assert result['segments']==[] and 'unavailable' in result['error']


def test_threshold_configuration(tmp_path):
    path=tmp_path/'config.toml';path.write_text('[cloud_forecast]\nclear_max_percent=15\n')
    assert load_cloud_settings(path)['clear_max_percent']==15
    path.write_text('[cloud_forecast]\nclear_max_percent=90\n')
    with pytest.raises(ValueError):load_cloud_settings(path)


def test_chart_cloud_payload_and_strip():
    import pandas as pd
    from interactive_chart import chart_html
    frame=pd.DataFrame({'Time':pd.to_datetime(['2026-10-30T18:00Z','2026-10-31T06:00Z']),'Altitude (°)':[40,50],'Azimuth (°)':[100,150]})
    forecast=dict(settings=DEFAULTS,segments=[dict(start=frame.Time[0].timestamp()*1000,end=frame.Time[0].timestamp()*1000+3600000,percent=35)],retrieved_at='2026-10-30T12:00:00+00:00',error=None)
    html=chart_html(frame,40,'Europe/London',cloud_forecast=forecast)
    payload=json.loads(html.split('const data=')[1].split(';')[0])
    assert payload['cloud_forecast']==forecast
    assert 'id="show-clouds"' in html
    assert "'data-cloud-cover'" in html and 'cloud-unavailable' in html
    assert "y2:visible('clouds')?cloudBottom:bottom" in html


def test_window_summary_weights_partial_hours_and_uses_full_window_percentage():
    from cloud_forecast import summarise_cloud_window
    start=datetime(2026,10,30,20,30,tzinfo=timezone.utc);base=start.timestamp()*1000-1800000
    data=dict(settings=DEFAULTS,retrieved_at=None,error=None,segments=[dict(start=base,end=base+3600000,percent=0),dict(start=base+3600000,end=base+7200000,percent=60)])
    summary=summarise_cloud_window(data,start,start+timedelta(hours=1,minutes=30))
    assert summary['average']==40 and summary['highest']==60
    assert summary['exceeded_duration']=='01:00'
    assert summary['exceeded_percent']==pytest.approx(100*2/3)
    assert summary['missing_seconds']==0
    summary=summarise_cloud_window(data,start,start+timedelta(hours=3))
    assert summary['average']==40 and summary['missing_duration']=='01:30'
    assert summary['exceeded_percent']==pytest.approx(100/3)


def test_window_summary_missing_is_never_clear():
    from cloud_forecast import summarise_cloud_window
    start=datetime(2026,10,25,0,tzinfo=timezone.utc)
    result=summarise_cloud_window(dict(settings=DEFAULTS,segments=[]),start,start+timedelta(hours=4))
    assert result['average'] is None and result['highest'] is None
    assert result['missing_duration']=='04:00'
