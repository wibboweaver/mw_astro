from datetime import datetime,timedelta,timezone
import pandas as pd
import pytest
from night_rating import DEFAULTS,score_window,usable_windows,load_rating_settings,rating_gauge
from astronomical_night import NightInterval

START=datetime(2026,11,4,18,tzinfo=timezone.utc)
A=START.timestamp(); B=A+7200

def forecast(cloud=0,rain=0,end=B):
    return dict(settings={'clear_max_percent':20},segments=[dict(start=A*1000,end=end*1000,percent=cloud)],precipitation_segments=[dict(start=A*1000,end=B*1000,percent=rain)])

def test_score_weights_and_separate_rain():
    assert score_window(A,B,forecast(),[],1,DEFAULTS)['score']==100
    assert score_window(A,B,forecast(100),[],1,DEFAULTS)['score']==100
    assert score_window(A,B,forecast(0,90),[],1,DEFAULTS)==dict(score=100,rain=90,cloud=0,reason=score_window(A,B,forecast(),[],1,DEFAULTS)['reason'])
    moon=[dict(start=A*1000,end=B*1000,level='strong')]
    assert score_window(A,B,forecast(),moon,1,DEFAULTS)['score']==79
    assert score_window(A,B,forecast(),[],0,DEFAULTS)['score']==60
    assert score_window(A,A+3600,forecast(),[],1,DEFAULTS)['score']==79

@pytest.mark.parametrize('cloud,moon,frame',[(forecast(),None,1),(forecast(),[],None)])
def test_missing_inputs_are_unknown(cloud,moon,frame):
    assert score_window(A,B,cloud,moon,frame,DEFAULTS)['score'] is None

def test_continuous_windows_interpolate_clearance_and_clip_darkness():
    frame=pd.DataFrame({'Time':[START,START+timedelta(hours=1),START+timedelta(hours=2)],'Altitude (°)':[30,50,30],'Azimuth (°)':[90,90,90]})
    windows=usable_windows(frame,40,None,[NightInterval(START,START+timedelta(hours=2))])
    assert windows==[(A+1800,A+5400)]
    assert not usable_windows(frame,60,None,[NightInterval(START,START+timedelta(hours=2))])

def test_rating_config_validation_and_gauge(tmp_path):
    path=tmp_path/'config.toml';path.write_text('[night_rating]\nframe_weight=70\n')
    assert load_rating_settings(path)['frame_weight']==70
    path.write_text('[night_rating]\nvisibility_weight=-1\n')
    with pytest.raises(ValueError):load_rating_settings(path)
    gauge=rating_gauge(87,'<test>')
    assert 'data:image/png;base64,' in gauge and 'Night rating 87 out of 100' in gauge and '&lt;test&gt;' in gauge


def test_frame_credit_and_cap_can_be_tuned():
    small=score_window(A,B,forecast(),[],.2,DEFAULTS)
    large=score_window(A,B,forecast(),[],1,DEFAULTS)
    assert small['score']==60 and large['score']==100
    assert small['cloud']==0
    linear=score_window(A,B,forecast(),[],.5,DEFAULTS)['score']
    stronger=score_window(A,B,forecast(),[],.5,dict(DEFAULTS,frame_curve_exponent=2))['score']
    assert stronger<linear
    uncapped=score_window(A,B,forecast(),[],.2,dict(DEFAULTS,undersized_score_cap=100))['score']
    assert uncapped>small['score']
    heavier=score_window(A,B,forecast(),[],.5,dict(DEFAULTS,frame_weight=75))['score']
    assert heavier<linear
    assert score_window(A,B,forecast(35),[],1,DEFAULTS)['cloud']==35

@pytest.mark.parametrize('key,value',[('preferred_frame_coverage_percent',0),('preferred_frame_coverage_percent',101),('frame_curve_exponent',0),('undersized_score_cap',101)])
def test_invalid_frame_rating_settings(tmp_path,key,value):
    path=tmp_path/'config.toml';path.write_text(f'[night_rating]\n{key}={value}\n')
    with pytest.raises(ValueError):load_rating_settings(path)


@pytest.mark.parametrize('score',[None,0,87,100])
def test_gauge_has_actual_png_image(score):
    from night_rating import rating_image
    from PIL import Image
    from io import BytesIO
    data=rating_image(score)
    assert data.startswith(b'\x89PNG\r\n\x1a\n')
    image=Image.open(BytesIO(data))
    assert image.size==(176,176)
    assert image.getbbox() is not None


def test_unknown_usable_targets_sort_before_zero_rated_targets():
    from night_rating import rating_sort_key
    values = {
        'daylight': dict(score=0, start=None, end=None),
        'unknown short': dict(score=None, start=A, end=A+3600),
        'unknown long': dict(score=None, start=A, end=B),
        'rated': dict(score=60, start=A, end=B),
    }
    assert sorted(values, key=lambda name: rating_sort_key(values[name], name)) == [
        'rated', 'unknown long', 'unknown short', 'daylight']


def test_november_27_has_visible_targets_even_without_a_forecast():
    from catalogue import load_catalogue
    from configuration import Settings
    from visibility import calculate_tracks
    from astronomical_night import night_for_chart
    from horizon import load_horizon
    from pathlib import Path
    from night_rating import all_ratings, rating_sort_key
    from planning import load_rules
    start=datetime(2026,11,27,17,tzinfo=timezone.utc)
    targets=tuple(t for t in load_catalogue() if t.object_id in ('NGC0224','NGC6853'))
    settings=Settings(latitude_deg=52.293232,longitude_deg=-3.036226,minimum_altitude_deg=50)
    profile=load_horizon(Path(__file__).resolve().parents[1]/'locations'/'Decking.txt')
    tracks=calculate_tracks(targets,settings.latitude_deg,settings.longitude_deg,40,start,16,10)
    end=start+timedelta(hours=16)
    nights=night_for_chart(start.date(),'Europe/London',start,end,settings.latitude_deg,settings.longitude_deg,40)
    cloud=dict(settings={'clear_max_percent':20},segments=[],error='No forecast available for this date')
    ratings=all_ratings(targets,tracks,nights,profile,50,cloud,settings,load_rules()['moon'],DEFAULTS)
    ordered=sorted(targets,key=lambda t:rating_sort_key(ratings[t.common_name],t.common_name))
    assert ordered[0].object_id=='NGC0224'
    andromeda=ratings[ordered[0].common_name]
    assert andromeda['score'] > 0 and andromeda['start'] is not None
    assert andromeda['end']-andromeda['start']>6*3600
    assert ratings[ordered[1].common_name]['score']==0


@pytest.mark.parametrize('weather', [forecast(), forecast(100,100), forecast(end=A+3600), dict(settings={'clear_max_percent':20},segments=[],error='No forecast available')])
def test_score_and_explanation_are_independent_of_weather(weather):
    baseline=score_window(A,B,forecast(),[],.5,DEFAULTS)
    actual=score_window(A,B,weather,[],.5,DEFAULTS)
    assert actual['score']==baseline['score']
    assert actual['reason']==baseline['reason']
    assert 'cloud' not in actual['reason'].lower()


@pytest.mark.parametrize('score', [None, 0, 87, 100])
def test_rating_digits_remain_legible_inside_the_circle(score):
    from io import BytesIO
    from PIL import Image
    from night_rating import rating_image
    image = Image.open(BytesIO(rating_image(score)))
    # This rectangle is inside the ring, so only the text contributes pixels.
    bounds = image.crop((32, 60, 144, 116)).getchannel('A').getbbox()
    assert bounds is not None
    assert bounds[3] - bounds[1] >= 35
