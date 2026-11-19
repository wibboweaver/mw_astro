"""Human-readable N.I.N.A. handover and observation assessment; no equipment control."""
from datetime import datetime
from filter_recommendations import recommend_dualband, catalogue_types, BROADBAND_TYPES
from object_sizes import normalise_id, frame_metrics
from framing import field_of_view
from cloud_forecast import summarise_cloud_window


def duration(seconds):
    minutes=round(seconds/60)
    return f'{minutes//60:02d}:{minutes%60:02d}'


def clean(value):
    return str(value).replace('|',r'\|').replace('\n',' ').replace('<','&lt;').replace('>','&gt;')


def markdown_report(plan,target,settings,assessment,cloud_data=None,frame_centre=None,night_rating=None):
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    coord=SkyCoord(target.ra_deg*u.deg,target.dec_deg*u.deg)
    ra=coord.ra.to_string(unit=u.hourangle,sep=':',precision=1,pad=True)
    dec=coord.dec.to_string(unit=u.deg,sep=':',precision=0,pad=True,alwayssign=True)
    frame_coord=SkyCoord(*(frame_centre or (target.ra_deg,target.dec_deg)),unit='deg')
    frame_ra=frame_coord.ra.to_string(unit=u.hourangle,sep=':',precision=1,pad=True)
    frame_dec=frame_coord.dec.to_string(unit=u.deg,sep=':',precision=0,pad=True,alwayssign=True)
    filter_yes,_=recommend_dualband(target.object_id)
    filter_label='Dualband Filter' if filter_yes else 'No filter' if catalogue_types().get(normalise_id(target.object_id)) in BROADBAND_TYPES else 'Unknown — object classification is inconclusive'
    footprint=frame_metrics(target.object_id,field_of_view(settings.focal_length_mm,settings.sensor_width_mm,settings.sensor_height_mm),(settings.camera_width_px,settings.camera_height_px),settings.min_frame_coverage_percent)
    rows=[('Target',f'{target.common_name} — {target.object_id}'),('Catalogue centre (J2000)',f'RA {ra} · Dec {dec}'),
          ('Frame centre (J2000)',f'RA {frame_ra} · Dec {frame_dec}'),
          ('Frame angle',f'{settings.frame_rotation_deg:g}°'),
          ('Capture starts',plan.start.strftime('%d %B %Y, %H:%M %Z (%z)')),('Capture ends',plan.end.strftime('%d %B %Y, %H:%M %Z (%z)')),
          ('Timezone',settings.timezone),('Exposure',f'{plan.exposure_seconds:g} seconds'),('Available duration',duration(plan.seconds)),
          ('Maximum exposures (before overheads)',str(assessment.exposures)),
          ('Filter recommendation',filter_label)]
    lines=[f'# Imaging Plan — {clean(target.common_name)}','']
    from night_rating import rating_gauge
    score=(night_rating or {}).get('score')
    reason=(night_rating or {}).get('reason','Night rating unavailable.')
    lines += ['<!-- NIGHT_RATING_START -->',rating_gauge(score,reason),'<!-- NIGHT_RATING_END -->','']
    if night_rating and night_rating.get('start') is not None:
        first=datetime.fromtimestamp(night_rating['start'],plan.start.tzinfo)
        last=datetime.fromtimestamp(night_rating['end'],plan.start.tzinfo)
        lines += [f'Rated window: {first:%d %b %Y %H:%M}–{last:%d %b %Y %H:%M %Z}. This is the object’s best rated window within the chart range; it may differ from the selected capture interval.','']
    lines += ['## Capture Information (NINA)','','| Setting | Planned value |','|---|---|']
    lines += [f'| {key} | {clean(value)} |' for key,value in rows]
    criteria=[]
    high={'Limited observation duration','Start altitude','End altitude','Start horizon','End horizon','Start night','End night','Cloud cover','Precipitation','Wind and dew','Sky conditions across window'}
    low={'Start timing'}
    def add(name,status,impact,notes):
        rating='High' if name in high else 'Low' if name in low else 'Medium'
        status={'Pass':'Favourable','Fail':'Review on site','Unknown':'Not assessed'}.get(status,status)
        criteria.append((name,status,rating,notes))
    combined=any(c.name=='Limited observation duration' for c in assessment.checks)
    for c in assessment.checks:
        if c.name in ('Frame fit','Frame containment'):
            continue
        if combined and c.name in ('Start altitude','End altitude','Start horizon','End horizon'):
            continue
        status='Pass' if c.status=='Suitable' else 'Unknown' if c.status=='Unknown' else 'Fail'
        notes=c.message
        add(c.name,status,'',notes)
    sky=assessment.sky_feedback
    if sky is not None:
        add('Sky conditions across window','Pass' if sky['twilight']<.5 and sky['brighter']<.5 else 'Fail','',
            f"Astronomical night: {duration(sky['night'])}; astronomical twilight: {duration(sky['twilight'])}; brighter conditions: {duration(sky['brighter'])}. Twilight may be usable depending on target, filter and actual background brightness.")
    coverage=footprint['coverage'].replace(' × ',' x ')
    pixels=footprint['pixels'].replace(' × ',' x ')
    notes=f"The selected object covers {coverage} of the frame which is approximately {pixels} pixels."
    status='Unknown' if footprint['status']=='Unknown' else 'Pass' if footprint['status']=='Pass' and not footprint['oversized'] else 'Fail'
    if footprint['status']=='Unknown':
        notes+=' Frame fit cannot be verified because catalogue dimensions are missing.'
    elif footprint['oversized']:
        notes+=' The object extends beyond the frame.'
    add('Frame fit',status,'',notes)
    moon=assessment.moon_feedback
    if moon and moon.get('enabled'):
        intervals=[]
        for interval in moon.get('intervals',[]):
            a=datetime.fromtimestamp(interval['start']/1000,plan.start.tzinfo)
            b=datetime.fromtimestamp(interval['end']/1000,plan.start.tzinfo)
            intervals.append(f'{a:%d %b %H:%M}–{b:%d %b %H:%M %Z}')
        notes=f"{moon['phase']}, {moon['illumination']:.0f}% illuminated; possible interference for {moon['duration']} ({moon['percent']:.0f}%)."
        if intervals:notes+=' Intervals: '+ '; '.join(intervals)+'.'
        add('Moon interference','Fail' if moon['percent']>0 else 'Pass','Raised background and reduced contrast.' if moon['percent']>0 else 'No significant interference predicted.',notes)
    else:
        add('Moon interference','Unknown','Moonlight may reduce contrast.','Assessment unavailable or disabled.')
    if cloud_data is not None:
        cloud=summarise_cloud_window(cloud_data,plan.start,plan.end)
        status='Unknown' if cloud['missing_seconds']>.5 else 'Fail' if cloud['exceeded_percent']>0 else 'Pass'
        notes=(f"Average {cloud['average']:.0f}%, maximum {cloud['highest']:.0f}%; above your {cloud['limit']:g}% preference for {cloud['exceeded_duration']} ({cloud['exceeded_percent']:.0f}%)." if cloud['average'] is not None else 'Cloud forecast unavailable.')
        if cloud['missing_seconds']>.5:notes+=f" Missing {cloud['missing_duration']}; missing data is not clear sky."
        add('Cloud cover',status,'Cloud can obscure the target and reduce usable exposures.' if status!='Pass' else 'Forecast stays within your cloud preference.',notes)
        rain=summarise_cloud_window(dict(cloud_data,segments=cloud_data.get('precipitation_segments',[])),plan.start,plan.end)
        status='Unknown' if rain['missing_seconds']>.5 else 'Fail' if (rain['highest'] or 0)>0 else 'Pass'
        notes=(f"Maximum hourly precipitation probability {rain['highest']:.0f}%; probability, not rainfall amount." if rain['highest'] is not None else 'Precipitation forecast unavailable.')
        if rain['missing_seconds']>.5:notes+=f" Missing {rain['missing_duration']}."
        add('Precipitation',status,'Rain can wet equipment; check conditions before capture.' if status!='Pass' else 'No precipitation indicated by the forecast.',notes)
    else:
        add('Cloud cover','Unknown','Cloud may reduce usable integration.','Forecast unavailable; verify conditions before capture.')
        add('Precipitation','Unknown','Rain can wet equipment.','Forecast unavailable; verify conditions before capture.')
    add('Wind and dew','Unknown','Wind can affect tracking; condensation can affect optics.','Wind, dew risk and live rain protection have not been assessed.')
    lines += ['','## Observation Criteria','','Confirm conditions at the telescope: inspect the sky and obstructions, and assess a trial exposure. These estimates support your judgement.','']
    for heading,passed in (('Favourable criteria',True),('Criteria to review on site',False)):
        lines += ['### '+heading,'','| Criterion | Status | Potential Impact | Notes |','|---|---|---|---|']
        selected=[row for row in criteria if (row[1]=='Favourable')==passed]
        lines += ['| '+' | '.join(clean(cell) for cell in row)+' |' for row in selected]
        if not selected:lines.append('| None | — | — | No criteria in this category. |')
        lines.append('')
    return '\n'.join(lines)

from pathlib import Path
_loaded_source_stamp=Path(__file__).stat().st_mtime_ns
