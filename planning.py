"""Offline imaging-session assessment. Acceptance never arms equipment."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import uuid
import tomllib
import numpy as np

DEFAULTS = {
    'enabled': True, 'allow_warning_override': True, 'allow_unknown_advisory_override': True,
    'darkness': dict(enabled=True, preferred_sun_altitude=-18., maximum_sun_altitude=-12.),
    'visibility': dict(enabled=True, preferred_min_altitude=40., absolute_min_altitude=30., horizon_clearance_margin=3., sample_interval_minutes=2),
    'moon': dict(enabled=True, broadband_min_separation=60., broadband_critical_separation=30., high_illumination_percent=70., low_illumination_percent=30., dualband_sensitivity_factor=.5),
    'integration': dict(enabled=True, preferred_minutes=90., minimum_minutes=30., preferred_exposures=30, minimum_exposures=10),
    'exposure': dict(enabled=True, min_seconds=1., max_seconds=600., download_overhead_seconds=3., dither_interval_exposures=3, dither_overhead_seconds=15., autofocus_overhead_seconds=180., meridian_flip_overhead_seconds=300., initial_setup_minutes=10.),
    'framing': dict(enabled=True, minimum_target_coverage_percent=100., preferred_edge_margin_percent=5.),
    'weather': dict(enabled=True, preferred_max_cloud_percent=20., warning_max_cloud_percent=50., preferred_max_wind_mph=15., warning_max_wind_mph=25., gust_warning_mph=20., humidity_warning_percent=85., humidity_critical_percent=95., dewpoint_margin_celsius=3., forecast_max_age_minutes=180.),
    'timing': dict(late_start_hour=23, early_hours_end=6),
    'filter': dict(enabled=True, warn_on_target_mismatch=True, require_filter_confirmation=True),
}


def load_rules(path=None):
    from configuration import CONFIG_PATH
    with Path(path or CONFIG_PATH).open('rb') as handle:
        supplied = tomllib.load(handle).get('planning_rules', {})
    def merge(default, values, prefix='planning_rules'):
        if not isinstance(values, dict) or values.keys() - default.keys():
            raise ValueError(f'Unknown or malformed {prefix} settings.')
        result = {}
        for key, original in default.items():
            value = values.get(key, original)
            name = f'{prefix}.{key}'
            if isinstance(original, dict):
                result[key] = merge(original, value, name)
            elif isinstance(original, bool):
                if type(value) is not bool:
                    raise ValueError(f'{name} must be true or false.')
                result[key] = value
            else:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f'{name} must be finite.')
                if key not in ('preferred_sun_altitude', 'maximum_sun_altitude') and value < 0:
                    raise ValueError(f'{name} must be nonnegative.')
                if key in ('sample_interval_minutes', 'dither_interval_exposures') and (type(value) is not int or value < 1):
                    raise ValueError(f'{name} must be a positive integer.')
                result[key] = value
        return result
    rules = merge(DEFAULTS, supplied)
    for section, low, high in [('darkness','preferred_sun_altitude','maximum_sun_altitude'), ('visibility','absolute_min_altitude','preferred_min_altitude'), ('moon','broadband_critical_separation','broadband_min_separation'), ('moon','low_illumination_percent','high_illumination_percent'), ('integration','minimum_minutes','preferred_minutes'), ('integration','minimum_exposures','preferred_exposures'), ('exposure','min_seconds','max_seconds'), ('weather','preferred_max_cloud_percent','warning_max_cloud_percent'), ('weather','preferred_max_wind_mph','warning_max_wind_mph'), ('weather','humidity_warning_percent','humidity_critical_percent')]:
        if rules[section][low] > rules[section][high]:
            raise ValueError(f'{section}: {low} must not exceed {high}.')
    if not 1 <= rules['visibility']['sample_interval_minutes'] <= 60:
        raise ValueError('Sampling interval must be 1–60 minutes.')
    for key, value in rules['timing'].items():
        if type(value) is not int or not 0 <= value <= 23:
            raise ValueError(f'timing.{key} must be an hour from 0 to 23.')
    for key in ('low_illumination_percent','high_illumination_percent'):
        if not 0 <= rules['moon'][key] <= 100:
            raise ValueError(f'moon.{key} must be 0 to 100 percent.')
    for key in ('broadband_min_separation','broadband_critical_separation'):
        if not 0 <= rules['moon'][key] <= 180:
            raise ValueError(f'moon.{key} must be 0 to 180 degrees.')
    return rules


@dataclass(frozen=True)
class Plan:
    target: str
    start: datetime
    end: datetime
    exposure_seconds: float
    filter_name: str = 'No filter'
    filter_confirmed: bool = False

    def __post_init__(self):
        for value in (self.start, self.end):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError('Session times must include a timezone.')
            if value.astimezone(timezone.utc).astimezone(value.tzinfo).replace(tzinfo=None) != value.replace(tzinfo=None):
                raise ValueError('Session time does not exist because of a clock change.')
        if not 0 < self.seconds <= 48*3600:
            raise ValueError('End must follow start, within 48 hours. Use explicit dates for overnight sessions.')
        if isinstance(self.exposure_seconds, bool) or not math.isfinite(self.exposure_seconds) or self.exposure_seconds <= 0:
            raise ValueError('Exposure must be positive and finite.')
        if self.filter_name not in ('No filter', 'DB2 dual-band'):
            raise ValueError('Unknown filter.')

    @property
    def seconds(self):
        return (self.end.astimezone(timezone.utc)-self.start.astimezone(timezone.utc)).total_seconds()


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    message: str


@dataclass
class Report:
    checks: list
    exposures: int
    integration_minutes: float
    moon_feedback: dict | None = None
    cloud_feedback: dict | None = None

    @property
    def status(self):
        for status in ('Unsuitable', 'Unknown', 'Challenging'):
            if any(c.status == status for c in self.checks):
                return status
        return 'Suitable'

    def can_accept(self, rules, acknowledged=False):
        states = {c.status for c in self.checks}
        return ('Unsuitable' not in states
                and ('Challenging' not in states or rules['allow_warning_override'] and acknowledged)
                and ('Unknown' not in states or rules['allow_unknown_advisory_override'] and acknowledged))



def visibility_durations(seconds, clearance, visible_clearance, sample_seconds=None):
    """Integrate linear sample crossings; return obscured time and longest clear run."""
    times = np.asarray(sample_seconds if sample_seconds is not None else np.linspace(0,seconds,len(clearance)),dtype=float)
    if len(times) != len(clearance) or len(times)<2 or times[0] != 0 or abs(times[-1]-seconds)>0.01 or np.any(np.diff(times)<=0):
        raise ValueError('Visibility samples must span the observation in chronological order.')
    def intervals(values):
        result=[]
        for index,(a,b) in enumerate(zip(values[:-1],values[1:])):
            start,end=times[index:index+2]
            if a>0 and b>0:
                result.append((start,end))
            elif (a>0) != (b>0):
                crossing=start+(end-start)*(-a)/(b-a)
                result.append((start,crossing) if a>0 else (crossing,end))
        merged=[]
        for start,end in result:
            if merged and abs(start-merged[-1][1])<1e-6:
                merged[-1]=(merged[-1][0],end)
            else:
                merged.append((start,end))
        return merged
    clear=intervals(np.asarray(clearance))
    visible=intervals(np.asarray(visible_clearance))
    return max(0.,seconds-sum(b-a for a,b in clear)),max((b-a for a,b in visible),default=0.)


def assess(plan, rules, *, altitudes, horizons, sun_altitudes, moon_altitudes,
           moon_separations, moon_illumination, crossing=False, filter_recommended=None,
           target_major_arcmin=None, fov=None, weather=None, now=None, sample_seconds=None):
    arrays = [np.asarray(x, dtype=float) for x in (altitudes, horizons, sun_altitudes, moon_altitudes, moon_separations, moon_illumination)]
    if any(a.ndim != 1 or not len(a) or not np.isfinite(a).all() for a in arrays) or len({len(a) for a in arrays}) != 1:
        raise ValueError('Sky samples must be finite, nonempty and aligned.')
    checks = []
    def add(name, status, message):
        checks.append(Check(name, status, message))
    def grade(value, hard, preferred):
        return 'Unsuitable' if value < hard else 'Challenging' if value < preferred else 'Suitable'
    e = rules['exposure']
    fixed = e['initial_setup_minutes']*60 + e['autofocus_overhead_seconds'] + (e['meridian_flip_overhead_seconds'] if crossing else 0)
    def cost(n):
        return fixed+n*(plan.exposure_seconds+e['download_overhead_seconds'])+max(0,(n-1)//e['dither_interval_exposures'])*e['dither_overhead_seconds']
    lo, hi = 0, int(plan.seconds/plan.exposure_seconds)+1
    while lo+1 < hi:
        mid = (lo+hi)//2
        if cost(mid) <= plan.seconds:
            lo = mid
        else:
            hi = mid
    count = lo
    minutes = count*plan.exposure_seconds/60
    if not rules['enabled']:
        return Report([Check('Validation', 'Unknown', 'Planning rules are disabled; enable validation before review.')], count, minutes)
    if e['enabled']:
        add('Exposure length', 'Suitable' if e['min_seconds'] <= plan.exposure_seconds <= e['max_seconds'] else 'Unsuitable', 'Exposure time is outside the allowed range')
    d = rules['darkness']
    if d['enabled']:
        peak = float(np.max(sun_altitudes))
        add('Astronomical darkness', 'Unsuitable' if peak > d['maximum_sun_altitude'] else 'Challenging' if peak > d['preferred_sun_altitude'] else 'Suitable', 'Observation includes time outside astronomical darkness')
        for name, value, message in (
            ('Start darkness',sun_altitudes[0],'Start time is before astronomical sunset'),
            ('End darkness',sun_altitudes[-1],'End time is after astronomical sunrise')):
            if value > d['preferred_sun_altitude']:
                add(name,'Unsuitable' if value > d['maximum_sun_altitude'] else 'Challenging',message)
    v = rules['visibility']
    if v['enabled']:
        minimum = float(np.min(altitudes))
        add('Target altitude', grade(minimum,v['absolute_min_altitude'],v['preferred_min_altitude']), f'Object drops to {minimum:.0f}° altitude')
        clearance = float(np.min(np.asarray(altitudes)-np.asarray(horizons)))
        add('Local horizon', 'Unsuitable' if clearance <= v['horizon_clearance_margin'] else 'Suitable', 'Object is obscured during the observation')
        clearances = np.asarray(altitudes)-np.asarray(horizons)-v['horizon_clearance_margin']
        if clearances[0] <= 0:
            add('Start obstruction','Unsuitable','Object is obscured at start time')
        if clearances[-1] <= 0:
            add('End obstruction','Unsuitable','Object is obscured at end time')
        visible_clearance=np.minimum(clearances,np.asarray(altitudes)-v['absolute_min_altitude'])
        obscured, longest = visibility_durations(plan.seconds,clearances,visible_clearance,sample_seconds)
        if obscured > .5:
            total_minutes=max(1,round(obscured/60))
            add('Obscured duration','Unsuitable',f'Object is obscured for {total_minutes//60:02d}:{total_minutes%60:02d} ({obscured/plan.seconds*100:.0f}%) of the total observation time')
        if longest < rules['integration']['preferred_minutes']*60:
            add('Visible window','Challenging',f'Visible window is only {longest/3600:.1f} hours')
    i = rules['integration']
    if i['enabled']:
        add('Exposure count',grade(count,i['minimum_exposures'],i['preferred_exposures']),f'Only {count} exposures are expected')
        add('Integration time',grade(minutes,i['minimum_minutes'],i['preferred_minutes']),f'Only {minutes:.0f} minutes of integration are expected')
    m = rules['moon']
    if m['enabled']:
        up = np.asarray(moon_altitudes) > 0
        separation = float(np.min(np.asarray(moon_separations)[up])) if up.any() else 180.
        illumination = float(np.max(np.asarray(moon_illumination)[up])) if up.any() else 0.
        factor = m['dualband_sensitivity_factor'] if plan.filter_name == 'DB2 dual-band' else 1
        status = 'Unsuitable' if separation < m['broadband_critical_separation']*factor and illumination >= m['high_illumination_percent'] else 'Challenging' if separation < m['broadband_min_separation']*factor and illumination >= m['low_illumination_percent'] else 'Suitable'
        add('Moon interference',status,f'Moon is bright and only {separation:.0f}° from the object')
    f = rules['filter']
    if f['enabled']:
        status = 'Unknown' if filter_recommended is None else 'Challenging' if f['warn_on_target_mismatch'] and filter_recommended != (plan.filter_name == 'DB2 dual-band') else 'Suitable'
        add('Filter suitability',status,'Filter suitability is unknown' if filter_recommended is None else 'Selected filter may not suit this object')
        if f['require_filter_confirmation']:
            add('Filter confirmation','Suitable' if plan.filter_confirmed else 'Challenging','Confirm the fitted filter')
    if rules['framing']['enabled']:
        fr = rules['framing']
        # A circular envelope is conservative at every camera/target rotation.
        ratio = min(fov)*60/target_major_arcmin if fov and target_major_arcmin else None
        add('Framing', 'Unknown' if ratio is None else 'Unsuitable' if ratio*100 < fr['minimum_target_coverage_percent'] else 'Challenging' if ratio < 1+2*fr['preferred_edge_margin_percent']/100 else 'Suitable', 'Object may not fit comfortably in the camera frame' if ratio else 'Check framing manually')
    add('Meridian crossing','Challenging' if crossing else 'Suitable','A meridian flip is expected')
    if rules['weather']['enabled']:
        w = rules['weather']
        required = ('cloud_percent','wind_mph','gust_mph','humidity_percent','temperature_celsius','dewpoint_celsius','rain','updated_at')
        if weather is None or any(key not in weather for key in required):
            add('Weather forecast','Unknown','Check cloud cover and weather before starting')
        else:
            numeric = [weather[key] for key in required if key not in ('rain', 'updated_at')]
            if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in numeric):
                raise ValueError('Forecast values must be finite numbers.')
            if type(weather['rain']) is not bool or weather['updated_at'].utcoffset() is None:
                raise ValueError('Forecast needs a rain boolean and timezone-aware update time.')
            updated = weather['updated_at']
            age = ((now or datetime.now(timezone.utc))-updated).total_seconds()/60
            if age < 0 or age > w['forecast_max_age_minutes']:
                add('Weather forecast','Unknown','Weather forecast needs updating')
            else:
                for label,key,preferred,maximum in (
                    ('Cloud cover','cloud_percent','preferred_max_cloud_percent','warning_max_cloud_percent'),
                    ('Wind','wind_mph','preferred_max_wind_mph','warning_max_wind_mph')):
                    value = weather[key]
                    add(label,'Unsuitable' if value > w[maximum] else 'Challenging' if value > w[preferred] else 'Suitable',f'Forecast {value:g}; review again before execution.')
                add('Rain','Unsuitable' if weather['rain'] else 'Suitable','Rain forecast.' if weather['rain'] else 'No rain in supplied forecast.')
                add('Gusts','Challenging' if weather['gust_mph'] > w['gust_warning_mph'] else 'Suitable',f'Forecast gusts {weather["gust_mph"]:g} mph.')
                humidity = weather['humidity_percent']
                add('Humidity','Unsuitable' if humidity > w['humidity_critical_percent'] else 'Challenging' if humidity > w['humidity_warning_percent'] else 'Suitable',f'Forecast humidity {humidity:g}%.')
                margin = weather['temperature_celsius']-weather['dewpoint_celsius']
                add('Dew point','Challenging' if margin <= w['dewpoint_margin_celsius'] else 'Suitable',f'Temperature–dew point margin {margin:g}°C.')
    return Report(checks,count,minutes)


def evaluate(plan, target, settings, rules, profile=None):
    import astropy.units as u
    from astropy.coordinates import EarthLocation, AltAz, SkyCoord, get_sun, get_body
    from astropy.time import Time
    from astropy.utils import iers
    from altitude import calculate_altitudes
    from horizon import horizon_altitudes
    from target_table import next_transits
    from filter_recommendations import catalogue_types, EMISSION_TYPES, BROADBAND_TYPES
    from object_sizes import normalise_id, catalogue_sizes
    from framing import field_of_view
    times, alt, az = calculate_altitudes(target.ra_deg,target.dec_deg,settings.latitude_deg,settings.longitude_deg,settings.height_m,plan.start,plan.seconds/3600,rules['visibility']['sample_interval_minutes'],include_azimuth=True)
    site = EarthLocation.from_geodetic(settings.longitude_deg*u.deg,settings.latitude_deg*u.deg,settings.height_m*u.m)
    epochs = Time(times)
    with iers.conf.set_temp('auto_download',False):
        horizontal = AltAz(obstime=epochs,location=site,pressure=0*u.hPa)
        sun = get_sun(epochs)
        moon = get_body('moon',epochs,site)
        coord = SkyCoord(target.ra_deg*u.deg,target.dec_deg*u.deg).transform_to(moon.frame)
        separation = coord.separation(moon).deg
        elongation = moon.separation(sun.transform_to(moon.frame)).rad
        illumination = (1-np.cos(elongation))*50
        sun_alt = sun.transform_to(horizontal).alt.deg
        moon_alt = moon.transform_to(horizontal).alt.deg
    kind = catalogue_types().get(normalise_id(target.object_id))
    recommended = True if kind in EMISSION_TYPES else False if kind in BROADBAND_TYPES else None
    size = catalogue_sizes().get(normalise_id(target.object_id))
    transit = next_transits([target],plan.start,settings.longitude_deg)[0]
    return assess(plan,rules,altitudes=alt,horizons=horizon_altitudes(profile,az) if profile is not None else np.zeros(len(alt)),sun_altitudes=sun_alt,moon_altitudes=moon_alt,moon_separations=separation,moon_illumination=illumination,crossing=plan.start.astimezone(timezone.utc) <= transit.astimezone(timezone.utc) <= plan.end.astimezone(timezone.utc),sample_seconds=[(t-times[0]).total_seconds() for t in times],filter_recommended=recommended,target_major_arcmin=size[0] if size else None,fov=field_of_view(settings.focal_length_mm,settings.sensor_width_mm,settings.sensor_height_mm))


def save_accepted(plan, report, rules, directory, acknowledged=False):
    from configuration import _atomic_write
    if not rules['enabled'] or not report.can_accept(rules,acknowledged):
        raise ValueError('Resolve blockers and acknowledge allowed advisories before accepting.')
    payload = dict(schema_version=1,status='accepted',execution_status='not_armed',accepted_at=datetime.now(timezone.utc).isoformat(),acknowledged=acknowledged,plan={**asdict(plan),'start':plan.start.isoformat(),'end':plan.end.isoformat()},report={'status':report.status,'checks':[asdict(c) for c in report.checks],'exposures':report.exposures,'integration_minutes':report.integration_minutes,'moon_feedback':report.moon_feedback,'cloud_feedback':report.cloud_feedback},rules=rules)
    directory = Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    destination = directory/(str(uuid.uuid4())+'.json')
    _atomic_write(destination,json.dumps(payload,indent=2,allow_nan=False)+'\n')
    return destination




def limited_observation_seconds(seconds, altitudes, horizons, minimum_altitude, sample_seconds=None):
    """Time below the altitude limit OR behind the horizon, with overlap counted once."""
    times=np.asarray(sample_seconds if sample_seconds is not None else np.linspace(0,seconds,len(altitudes)),dtype=float)
    altitude_clearance=np.asarray(altitudes)-minimum_altitude
    horizon_clearance=np.asarray(altitudes)-np.asarray(horizons)
    total=0.
    for i in range(len(times)-1):
        a,b=altitude_clearance[i:i+2]
        c,d=horizon_clearance[i:i+2]
        cuts=[0.,1.]
        for first,last in ((a,b),(c,d)):
            if first!=last:
                crossing=-first/(last-first)
                if 0<crossing<1:
                    cuts.append(float(crossing))
        cuts=sorted(set(cuts))
        for left,right in zip(cuts[:-1],cuts[1:]):
            mid=(left+right)/2
            if a+(b-a)*mid<0 or c+(d-c)*mid<=0:
                total+=(times[i+1]-times[i])*(right-left)
    return float(total)


def checklist_report(plan, rules, minimum_altitude, altitudes, horizons, sun_altitudes, exposures, sample_seconds=None):
    """The fixed checklist displayed in Observation Feedback."""
    checks=[]
    def row(name, ok, yes, no, blocker=False):
        checks.append(Check(name,'Suitable' if ok else 'Unsuitable' if blocker else 'Challenging',yes if ok else no))
    for index, label in ((0,'Start'),(-1,'End')):
        row(f'{label} altitude',altitudes[index]>=minimum_altitude,
            f'Object is above the minimum altitude ({minimum_altitude:g}°)',
            f'Object is below the minimum altitude ({minimum_altitude:g}°)',True)
        row(f'{label} horizon',altitudes[index]>horizons[index],
            'Object is above the local horizon','Object is below the local horizon',True)
        row(f'{label} night',sun_altitudes[index]<=rules['darkness']['preferred_sun_altitude'],
            'Astronomical night is occurring','Astronomical night is not occurring',True)
    hours=plan.seconds/3600
    row('Observation duration',plan.seconds>=rules['integration']['preferred_minutes']*60,
        f'Total observation time is sufficient ({hours:.1f} hours)',
        f'Total observation time may be too short ({hours:.1f} hours)')
    row('Exposure count',exposures>=rules['integration']['preferred_exposures'],
        f'Number of exposures is sufficient ({exposures})',
        f'Number of exposures is small ({exposures})')
    hour=plan.start.hour
    timing=rules['timing']
    early=hour<timing['early_hours_end']
    late=hour>=timing['late_start_hour']
    row('Start timing',not (early or late),'Observation starts at a convenient time',
        'Observation begins in the early hours' if early else 'Observation does not begin until late')
    clearance=np.asarray(altitudes)-np.asarray(horizons)
    obscured,_=visibility_durations(plan.seconds,clearance,clearance,sample_seconds)
    total_minutes=round(obscured/60)
    percentage=obscured/plan.seconds*100
    checks.append(Check('Obscured duration','Suitable' if obscured<.5 else 'Unsuitable',
        f'The object is obscured for {total_minutes//60:02d}:{total_minutes%60:02d} ({percentage:.0f} %) of the total observation time'))
    limited=limited_observation_seconds(plan.seconds,altitudes,horizons,minimum_altitude,sample_seconds)
    limited_minutes=round(limited/60)
    checks.append(Check('Limited observation duration','Suitable' if limited<.5 else 'Unsuitable',
        f'The object is either below the minimum specified altitude or obscured by the local horizon for {limited_minutes//60:02d}:{limited_minutes%60:02d} ({limited/plan.seconds*100:.0f} %) of the total observation time'))
    return Report(checks,exposures,exposures*plan.exposure_seconds/60)


def evaluate_checklist(plan, target, settings, rules, profile=None, moon_data=None):
    import astropy.units as u
    from astropy.coordinates import EarthLocation, AltAz, get_sun
    from astropy.time import Time
    from astropy.utils import iers
    from altitude import calculate_altitudes
    from horizon import horizon_altitudes
    from target_table import next_transits
    times,alt,az=calculate_altitudes(target.ra_deg,target.dec_deg,settings.latitude_deg,settings.longitude_deg,settings.height_m,plan.start,plan.seconds/3600,rules['visibility']['sample_interval_minutes'],include_azimuth=True)
    site=EarthLocation.from_geodetic(settings.longitude_deg*u.deg,settings.latitude_deg*u.deg,settings.height_m*u.m)
    with iers.conf.set_temp('auto_download',False):
        sun=get_sun(Time(times)).transform_to(AltAz(obstime=Time(times),location=site,pressure=0*u.hPa)).alt.deg
    exposures=math.floor(math.floor(plan.seconds+0.5)/plan.exposure_seconds)
    report=checklist_report(plan,rules,settings.minimum_altitude_deg,alt,horizon_altitudes(profile,az) if profile is not None else np.zeros(len(alt)),sun,exposures,sample_seconds=[(t-times[0]).total_seconds() for t in times])
    if moon_data is not None:
        from moon_interference import window_feedback
        report.moon_feedback=window_feedback(moon_data,plan.start,plan.end)
    return report
