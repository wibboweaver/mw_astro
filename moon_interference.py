"""Estimated broadband moonlight interference, shared by chart and feedback."""
from datetime import datetime, timezone, timedelta
import numpy as np


def phase_name(angle):
    return ('New Moon','Waxing crescent','First quarter','Waxing gibbous','Full Moon','Waning gibbous','Last quarter','Waning crescent')[int((angle%360+22.5)//45)%8]


def interference_intervals(times, altitudes, illumination, separation, rules):
    """Interpolate threshold crossings and merge adjacent periods of equal severity."""
    if not rules['enabled']:
        return []
    times=np.asarray(times,dtype=float)
    arrays=[np.asarray(v,dtype=float) for v in (altitudes,illumination,separation)]
    if len(times)<2 or any(len(v)!=len(times) or not np.isfinite(v).all() for v in arrays) or not np.isfinite(times).all() or np.any(np.diff(times)<=0):
        raise ValueError('Invalid Moon samples.')
    result=[]
    for i in range(len(times)-1):
        cuts={0.,1.}
        thresholds=((arrays[0],0),(arrays[1],rules['low_illumination_percent']),(arrays[1],rules['high_illumination_percent']),(arrays[2],rules['broadband_min_separation']),(arrays[2],rules['broadband_critical_separation']))
        for values,threshold in thresholds:
            a,b=values[i:i+2]
            if a!=b:
                f=(threshold-a)/(b-a)
                if 0<f<1:cuts.add(float(f))
        cuts=sorted(cuts)
        for left,right in zip(cuts[:-1],cuts[1:]):
            mid=(left+right)/2
            altitude,lit,distance=[v[i]+(v[i+1]-v[i])*mid for v in arrays]
            if altitude<=0 or lit<rules['low_illumination_percent'] or not (distance<=rules['broadband_min_separation'] or lit>=rules['high_illumination_percent']):
                continue
            level='strong' if lit>=rules['high_illumination_percent'] and distance<=rules['broadband_critical_separation'] else 'possible'
            start=times[i]+(times[i+1]-times[i])*left
            end=times[i]+(times[i+1]-times[i])*right
            if result and result[-1]['level']==level and abs(result[-1]['end']-start)<.01:
                result[-1]['end']=end
            else:result.append(dict(start=start,end=end,level=level))
    return result


def calculate_moonlight(first,last,latitude,longitude,height,ra,dec,step_minutes,rules):
    import astropy.units as u
    from astropy.coordinates import EarthLocation, AltAz, SkyCoord, get_body, get_sun, get_body_barycentric, solar_system_ephemeris, GeocentricTrueEcliptic
    from astropy.time import Time
    from astropy.utils import iers
    first=first.astimezone(timezone.utc);last=last.astimezone(timezone.utc)
    offsets=np.append(np.arange(0,(last-first).total_seconds(),step_minutes*60),(last-first).total_seconds())
    stamps=[first+timedelta(seconds=float(v)) for v in offsets]
    epochs=Time(stamps)
    site=EarthLocation.from_geodetic(longitude*u.deg,latitude*u.deg,height*u.m)
    with iers.conf.set_temp('auto_download',False),solar_system_ephemeris.set('builtin'):
        moon=get_body('moon',epochs,site)
        alt=moon.transform_to(AltAz(obstime=epochs,location=site,pressure=0*u.hPa)).alt.deg
        target=SkyCoord(ra*u.deg,dec*u.deg).transform_to(moon.frame)
        separation=target.separation(moon).deg
        sunpos=get_body_barycentric('sun',epochs).xyz.value
        moonpos=get_body_barycentric('moon',epochs).xyz.value
        earthpos=get_body_barycentric('earth',epochs).xyz.value
        a=sunpos-moonpos;b=earthpos-moonpos
        cosine=np.sum(a*b,axis=0)/(np.linalg.norm(a,axis=0)*np.linalg.norm(b,axis=0))
        lit=(1+np.clip(cosine,-1,1))*50
        ecliptic=GeocentricTrueEcliptic(obstime=epochs,equinox=epochs)
        geocentric_moon=get_body('moon',epochs)
        phase=(geocentric_moon.transform_to(ecliptic).lon.deg-get_sun(epochs).transform_to(ecliptic).lon.deg)%360
    millis=[s.timestamp()*1000 for s in stamps]
    return dict(intervals=interference_intervals(millis,alt,lit,separation,rules),times=millis,illumination=lit.tolist(),phase_angles=phase.tolist(),enabled=rules['enabled'])


def window_feedback(data,start,end):
    first=start.timestamp()*1000;last=end.timestamp()*1000
    intervals=[]
    for item in data['intervals']:
        a=max(first,item['start']);b=min(last,item['end'])
        if b<=a:continue
        if intervals and abs(intervals[-1]['end']-a)<.01:intervals[-1]['end']=b
        else:intervals.append(dict(start=a,end=b))
    seconds=sum(i['end']-i['start'] for i in intervals)/1000
    angle=float(np.interp(first,data['times'],np.unwrap(np.radians(data['phase_angles']))))*180/np.pi
    illumination=float(np.interp(first,data['times'],data['illumination']))
    minutes=round(seconds/60)
    return dict(intervals=intervals,percent=seconds/((last-first)/1000)*100,duration=f'{minutes//60:02d}:{minutes%60:02d}',phase=phase_name(angle),illumination=illumination,enabled=data['enabled'])
