"""Preference-based night scores: not a probability of imaging success."""
from datetime import datetime,timezone
import math
from pathlib import Path
import tomllib
import numpy as np
from cloud_forecast import summarise_cloud_window
from object_sizes import catalogue_sizes,normalise_id
from horizon import horizon_altitudes

DEFAULTS={'visibility_weight':30.,'moon_weight':15.,'frame_weight':25.,'preferred_window_minutes':120.,'preferred_frame_coverage_percent':50.,'frame_curve_exponent':1.,'undersized_score_cap':60.}

def load_rating_settings(path):
    with Path(path).open('rb') as f:values=tomllib.load(f).get('night_rating',{})
    if values.keys()-DEFAULTS.keys():raise ValueError('Unknown night_rating setting.')
    result=DEFAULTS|values
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in result.values()):raise ValueError('Night rating values must be finite and nonnegative.')
    if result['preferred_window_minutes']<=0 or sum(result[k] for k in result if k.endswith('_weight'))<=0:raise ValueError('Night rating needs positive duration and total weight.')
    if not 0<result['preferred_frame_coverage_percent']<=100 or result['frame_curve_exponent']<=0 or not 0<=result['undersized_score_cap']<=100:
        raise ValueError('Frame coverage must be 0–100 (exclusive of zero), exponent positive, and undersized score cap 0–100.')
    return result

def usable_windows(frame,minimum,profile,nights):
    times=np.array([t.timestamp() for t in frame['Time']]);alt=frame['Altitude (°)'].to_numpy()
    horizon=horizon_altitudes(profile,frame['Azimuth (°)'].to_numpy()) if profile is not None else np.zeros(len(alt))
    intervals=[]
    for i in range(len(times)-1):
        a,b=alt[i:i+2]-minimum;c,d=alt[i:i+2]-horizon[i:i+2]
        if not np.isfinite([a,b,c,d]).all():continue
        cuts={0.,1.}
        for first,last in ((a,b),(c,d)):
            if first!=last and 0<-first/(last-first)<1:cuts.add(float(-first/(last-first)))
        cuts=sorted(cuts)
        for left,right in zip(cuts,cuts[1:]):
            mid=(left+right)/2
            if a+(b-a)*mid<0 or c+(d-c)*mid<=0:continue
            for night in nights:
                start=max(times[i]+(times[i+1]-times[i])*left,night.start.timestamp())
                end=min(times[i]+(times[i+1]-times[i])*right,night.end.timestamp())
                if end>start:
                    if intervals and abs(intervals[-1][1]-start)<.01:intervals[-1]=(intervals[-1][0],end)
                    else:intervals.append((start,end))
    return intervals

def score_window(start,end,cloud,moon,frame_fraction,rules,minimum_frame_fraction=0.3):
    first=datetime.fromtimestamp(start,timezone.utc);last=datetime.fromtimestamp(end,timezone.utc)
    weather=summarise_cloud_window(cloud,first,last)
    rain=summarise_cloud_window(dict(cloud,segments=cloud.get('precipitation_segments',[])),first,last)
    risk=rain['highest'] if rain['missing_seconds']<.5 else None
    cloud_average=weather['average'] if weather['missing_seconds']<.5 else None
    if moon is None:return dict(score=None,rain=risk,cloud=cloud_average,reason='Moon assessment unavailable or disabled.')
    if frame_fraction is None:return dict(score=None,rain=risk,cloud=cloud_average,reason='Catalogue dimensions unavailable; frame suitability cannot be assessed.')
    penalty=0.
    for interval in moon:
        overlap=max(0,min(end,interval['end']/1000)-max(start,interval['start']/1000))
        penalty+=overlap*(1 if interval['level']=='strong' else .5)/(end-start)
    factors={'visibility':min(1,(end-start)/(rules['preferred_window_minutes']*60)),'moon':max(0,1-penalty),'frame':max(0,min(1,frame_fraction))**rules['frame_curve_exponent']}
    total=sum(rules[k+'_weight'] for k in factors)
    score=round(100*sum(v*rules[k+'_weight'] for k,v in factors.items())/total)
    capped=frame_fraction<minimum_frame_fraction and rules['frame_weight']>0
    if capped:score=min(score,round(rules['undersized_score_cap']))
    reason=f"Continuous dark window {(end-start)/3600:.1f} h; Moon interference {penalty*100:.0f}% weighted; full-frame suitability {factors['frame']*100:.0f}%."
    if capped:reason+=f" Object is below minimum full-frame coverage; score capped at {rules['undersized_score_cap']:g}."
    return dict(score=score,rain=risk,cloud=cloud_average,reason=reason)

def all_ratings(targets,tracks,nights,profile,minimum,cloud,settings,moon_rules,rules):
    """Calculate Moon ephemerides once and transform target separations in a batch."""
    from moon_interference import calculate_moonlight,interference_intervals
    import astropy.units as u
    from astropy.coordinates import SkyCoord,EarthLocation,get_body
    from astropy.time import Time
    from astropy.utils import iers
    from framing import field_of_view
    moon_by_name={}
    if targets and moon_rules['enabled'] and nights:
        reference=targets[0];frame=tracks[reference.common_name]
        try:
            data=calculate_moonlight(frame.Time.iloc[0].to_pydatetime(),frame.Time.iloc[-1].to_pydatetime(),settings.latitude_deg,settings.longitude_deg,settings.height_m,reference.ra_deg,reference.dec_deg,settings.step_minutes,moon_rules)
            site=EarthLocation.from_geodetic(settings.longitude_deg*u.deg,settings.latitude_deg*u.deg,settings.height_m*u.m)
            with iers.conf.set_temp('auto_download',False):
                moon=get_body('moon',Time(np.array(data['times'])/1000,format='unix'),site)
                coordinates=SkyCoord(np.array([t.ra_deg for t in targets])[:,None]*u.deg,np.array([t.dec_deg for t in targets])[:,None]*u.deg)
                separations=coordinates.transform_to(moon.frame).separation(moon).deg
            moon_by_name={t.common_name:interference_intervals(data['times'],data['altitudes'],data['illumination'],separation,moon_rules) for t,separation in zip(targets,separations)}
        except (ValueError,TypeError,OSError):pass
    field=sorted(field_of_view(settings.focal_length_mm,settings.sensor_width_mm,settings.sensor_height_mm),reverse=True)
    results={}
    for target in targets:
        windows=usable_windows(tracks[target.common_name],minimum,profile,nights)
        sizes=catalogue_sizes().get(normalise_id(target.object_id))
        fraction=None if sizes is None or None in sizes else max(size/(side*60)*100/rules['preferred_frame_coverage_percent'] for size,side in zip(sizes,field))
        candidates=[]
        for start,end in windows:
            value=score_window(start,end,cloud,moon_by_name.get(target.common_name),fraction,rules,settings.min_frame_coverage_percent/rules['preferred_frame_coverage_percent'])
            if fraction is not None:value['reason']+=f" Object coverage (largest aligned dimension): {fraction*rules['preferred_frame_coverage_percent']:.1f}%; full-credit preference: {rules['preferred_frame_coverage_percent']:g}%."
            value.update(start=start,end=end)
            candidates.append(value)
        # Do not hide incomplete data by choosing a different, shorter window.
        if candidates:
            known=[c for c in candidates if c['score'] is not None]
            best=max(known,key=lambda c:(c['score'],c['end']-c['start'])) if known else max(candidates,key=lambda c:c['end']-c['start'])
        else:best=dict(score=0,rain=None,cloud=None,reason='No continuous dark window above both altitude and local horizon limits.',start=None,end=None)
        results[target.common_name]=best
    return results


def rating_sort_key(rating, name):
    """Keep usable but unassessed targets ahead of known unsuitable targets."""
    score = rating['score']
    group = 1 if score is None else 0 if score > 0 else 2
    duration = (rating.get('end') or 0) - (rating.get('start') or 0)
    return group, -(score or 0), -duration if score is None else 0, name.casefold()


def rating_image(score):
    """Return PNG bytes; HTML sanitizers can remove inline SVG graphics."""
    from PIL import Image,ImageDraw,ImageFont
    from io import BytesIO
    score=None if score is None else max(0,min(100,int(score)))
    colour='#888888' if score is None else '#22c55e' if score>=75 else '#f59e0b' if score>=50 else '#ef4444'
    image=Image.new('RGBA',(176,176),(0,0,0,0));draw=ImageDraw.Draw(image)
    draw.ellipse((16,16,160,160),outline='#666666',width=12)
    if score is not None and score>0:draw.arc((16,16,160,160),-90,-90+score*3.6,fill=colour,width=12)
    # Use Pillow's bundled scalable font so every platform has legible digits.
    # Render at twice the display resolution: 64 px becomes 32 px in the gauge.
    font=ImageFont.load_default(size=64)
    draw.text((88,88),'?' if score is None else str(score),font=font,fill=colour,anchor='mm')
    out=BytesIO();image.save(out,format='PNG');return out.getvalue()


def rating_gauge(score,reason,title='Night rating — based on the object’s observable window within the chart period'):
    from html import escape
    from base64 import b64encode
    score=None if score is None else max(0,min(100,int(score)))
    label='Night rating: Missing data' if score is None else f'Night rating {score} out of 100'
    source='data:image/png;base64,'+b64encode(rating_image(score)).decode('ascii')
    explanation=('Missing data — ' if score is None else '')+reason
    return f'<div style="display:flex;align-items:center;gap:16px"><img src="{source}" width="88" height="88" alt="{label}" style="flex:none"/><div><strong>{escape(title)}</strong><br>{escape(explanation)}<br><small>Preference score, not a probability of success.</small></div></div>'

_loaded_source_stamp=Path(__file__).stat().st_mtime_ns
