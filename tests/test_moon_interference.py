from datetime import datetime, timezone, timedelta
from copy import deepcopy
import pytest
from moon_interference import interference_intervals, window_feedback, phase_name, calculate_moonlight
from planning import DEFAULTS


def rules():return deepcopy(DEFAULTS['moon'])


def test_thresholds_and_astronomical_horizon():
    assert interference_intervals([0,1000],[-10,-1],[100,100],[5,5],rules())==[]
    assert interference_intervals([0,1000],[10,20],[10,10],[5,5],rules())==[]
    assert interference_intervals([0,1000],[10,20],[50,50],[100,100],rules())==[]
    assert interference_intervals([0,1000],[10,20],[90,90],[100,100],rules())[0]['level']=='possible'
    assert interference_intervals([0,1000],[10,20],[90,90],[20,20],rules())[0]['level']=='strong'
    assert interference_intervals([0,1000],[-10,10],[90,90],[20,20],rules())[0]['start']==500


def test_multiple_periods_clipping_and_full_window_denominator():
    start=datetime(2026,10,30,20,tzinfo=timezone.utc);base=start.timestamp()*1000
    data=dict(enabled=True,intervals=[dict(start=base,end=base+3600000,level='possible'),dict(start=base+7200000,end=base+10800000,level='strong')],times=[base,base+14400000],illumination=[80,81],phase_angles=[120,122])
    result=window_feedback(data,start+timedelta(minutes=30),start+timedelta(hours=3,minutes=30))
    assert len(result['intervals'])==2
    assert result['duration']=='01:30' and result['percent']==50
    assert result['phase']=='Waxing gibbous'
    empty=window_feedback(data,start+timedelta(hours=1),start+timedelta(hours=2))
    assert empty['percent']==0 and empty['duration']=='00:00'


@pytest.mark.parametrize('angle,name',[(0,'New Moon'),(45,'Waxing crescent'),(90,'First quarter'),(135,'Waxing gibbous'),(180,'Full Moon'),(225,'Waning gibbous'),(270,'Last quarter'),(315,'Waning crescent'),(359,'New Moon')])
def test_phase_names(angle,name):assert phase_name(angle)==name


def test_disabled_and_invalid_samples():
    r=rules();r['enabled']=False
    assert interference_intervals([0,1000],[10,20],[90,90],[10,20],r)==[]
    with pytest.raises(ValueError):interference_intervals([1000,0],[10,20],[90,90],[10,20],rules())


def test_real_ephemeris_illumination_and_no_minimum_altitude_dependency():
    first=datetime(2024,4,8,18,tzinfo=timezone.utc)
    data=calculate_moonlight(first,first+timedelta(hours=1),52,-3,40,10,40,2,rules())
    assert max(data['illumination'])<1
    assert phase_name(data['phase_angles'][0])=='New Moon'
    assert data['intervals']==[]
