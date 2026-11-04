"""Hourly cloud cover and precipitation probability from Open-Meteo; all internal times are UTC."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import math
import tomllib
from urllib.parse import urlencode
from urllib.request import urlopen

DEFAULTS=dict(enabled=True,clear_max_percent=20,light_max_percent=50,medium_max_percent=80)
ENDPOINT='https://api.open-meteo.com/v1/forecast'


def load_cloud_settings(path):
    with Path(path).open('rb') as handle:values=tomllib.load(handle).get('cloud_forecast',{})
    if values.keys()-DEFAULTS.keys():raise ValueError('Unknown cloud_forecast setting.')
    result=DEFAULTS|values
    if type(result['enabled']) is not bool:raise ValueError('cloud_forecast.enabled must be true or false.')
    limits=[result[k] for k in ('clear_max_percent','light_max_percent','medium_max_percent')]
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=100 for v in limits) or limits!=sorted(limits):
        raise ValueError('Cloud cover thresholds must increase from 0 to 100 percent.')
    return result


def fetch_cloud_forecast(latitude,longitude):
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not -90<=latitude<=90 or not -180<=longitude<=180:
        raise ValueError('Invalid forecast coordinates.')
    url=ENDPOINT+'?'+urlencode(dict(latitude=latitude,longitude=longitude,hourly='cloud_cover,precipitation_probability',forecast_days=16,timeformat='unixtime',timezone='UTC'))
    with urlopen(url,timeout=8) as response:body=response.read(1024*1024+1)
    if len(body)>1024*1024:raise ValueError('Forecast response is too large.')
    data=json.loads(body)
    hourly=data['hourly'];times=hourly['time'];values=hourly['cloud_cover']
    if data.get('hourly_units',{}).get('cloud_cover')!='%' or len(times)!=len(values) or not times:
        raise ValueError('Invalid cloud forecast response.')
    rain=hourly.get('precipitation_probability',[None]*len(times))
    if len(rain)!=len(times) or ('precipitation_probability' in hourly and data.get('hourly_units',{}).get('precipitation_probability')!='%'):
        raise ValueError('Invalid precipitation forecast response.')
    segments=[];precipitation_segments=[];previous=None
    for stamp,value,probability in zip(times,values,rain):
        if isinstance(stamp,bool) or not isinstance(stamp,(int,float)) or not math.isfinite(stamp) or previous is not None and stamp<=previous:
            raise ValueError('Invalid forecast timestamp.')
        previous=stamp
        if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=100):
            raise ValueError('Invalid cloud cover percentage.')
        if probability is not None and (isinstance(probability,bool) or not isinstance(probability,(int,float)) or not math.isfinite(probability) or not 0<=probability<=100):
            raise ValueError('Invalid precipitation probability.')
        segments.append(dict(start=stamp*1000,end=(stamp+3600)*1000,percent=value))
        # Open-Meteo precipitation probability describes the preceding hour.
        precipitation_segments.append(dict(start=(stamp-3600)*1000,end=stamp*1000,percent=probability))
    return dict(segments=segments,precipitation_segments=precipitation_segments,retrieved_at=datetime.now(timezone.utc).isoformat(),error=None)


def forecast_for_chart(first,last,latitude,longitude,settings,fetcher=fetch_cloud_forecast,now=None):
    now=now or datetime.now(timezone.utc)
    if not settings['enabled']:return dict(segments=[],retrieved_at=None,error='Cloud forecast disabled',settings=settings)
    today=now.astimezone(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
    if last<=today or first>=today+timedelta(days=16):
        return dict(segments=[],retrieved_at=None,error='No forecast available for this date',settings=settings)
    try:
        result=fetcher(latitude,longitude)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        result=dict(segments=[],retrieved_at=None,error='Cloud forecast unavailable — retry later')
    return dict(result,settings=settings)


def summarise_cloud_window(data,start,end):
    """Weight hourly blocks by their actual overlap with the selected UTC window."""
    first=start.timestamp()*1000;last=end.timestamp()*1000
    if last<=first:raise ValueError('Cloud summary needs a positive observation window.')
    covered=weighted=exceeded=0.;highest=None;previous=first
    limit=data['settings']['clear_max_percent']
    for block in sorted(data.get('segments',[]),key=lambda b:b['start']):
        a=max(first,block['start']);b=min(last,block['end']);value=block['percent']
        if b<=a:continue
        if a<previous:raise ValueError('Overlapping cloud forecast blocks.')
        previous=b
        if value is None:continue
        seconds=(b-a)/1000
        covered+=seconds;weighted+=value*seconds
        highest=value if highest is None else max(highest,value)
        if value>limit:exceeded+=seconds
    total=(last-first)/1000
    def duration(seconds):
        minutes=round(seconds/60)
        return f'{minutes//60:02d}:{minutes%60:02d}'
    missing=max(0.,total-covered)
    return dict(average=weighted/covered if covered else None,highest=highest,limit=limit,
                exceeded_percent=exceeded/total*100,exceeded_duration=duration(exceeded),
                missing_duration=duration(missing),missing_seconds=missing,
                covered_seconds=covered,retrieved_at=data.get('retrieved_at'),error=data.get('error'))


def chart_weather_summary(data,start,end):
    """One shared weather summary for every target over the full chart range."""
    cloud=summarise_cloud_window(data,start,end)
    rain=summarise_cloud_window(dict(data,segments=data.get('precipitation_segments',[])),start,end)
    return dict(cloud=cloud['average'] if cloud['missing_seconds']<.5 else None,
                rain=rain['highest'] if rain['missing_seconds']<.5 else None)

_loaded_source_stamp=Path(__file__).stat().st_mtime_ns
