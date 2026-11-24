"""Select a conservative capture window from existing sky and forecast data."""
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from capture_guidance import capture_guidance
from night_rating import usable_windows
from target_table import next_transits


def filter_choice(target):
    mode = capture_guidance(target.object_id).mode
    if mode in ('Dual-band', 'Both'):
        return 'Hα/O III dual-band' + ('; broadband separately if desired' if mode == 'Both' else ''), True
    if mode == 'Broadband':
        return 'Broadband (no dual-band filter)', False
    return 'Needs assessment — confirm the target/filter combination', False


def exposure_budget(seconds, exposure, rules, crossing=False):
    e = rules['exposure']
    if not e['enabled']:
        return int(seconds // exposure), 0.0
    fixed = e['initial_setup_minutes'] * 60 + e['autofocus_overhead_seconds']
    if crossing:
        fixed += e['meridian_flip_overhead_seconds']
    def overhead(count):
        return (fixed + count * e['download_overhead_seconds'] +
                max(0, (count - 1) // e['dither_interval_exposures']) * e['dither_overhead_seconds'])
    low, high = 0, int(seconds // exposure) + 1
    while low + 1 < high:
        middle = (low + high) // 2
        if middle * exposure + overhead(middle) <= seconds:
            low = middle
        else:
            high = middle
    return low, overhead(low)


def parameters_for_window(plan, target, settings, rules):
    transit = next_transits([target], plan.start, settings.longitude_deg)[0]
    crossing = plan.start.timestamp() <= transit.timestamp() <= plan.end.timestamp()
    count, overhead = exposure_budget(plan.seconds, plan.exposure_seconds, rules, crossing)
    selected_filter, _ = filter_choice(target)
    return dict(exposure_count=count, exposure_seconds=plan.exposure_seconds,
                integration_seconds=count * plan.exposure_seconds,
                overhead_seconds=overhead, meridian_flip=crossing,
                filter_type=selected_filter,
                points=[round(plan.start.timestamp() * 1000), round(plan.end.timestamp() * 1000)])


def darkness_windows(frame, nights, settings, rules, selection):
    first, last = frame.Time.iloc[0].timestamp(), frame.Time.iloc[-1].timestamp()
    threshold = -18. if selection['modes']['astronomical_night'] == 'mandatory' else rules['darkness']['maximum_sun_altitude']
    if threshold == -18:
        return nights
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, get_sun
    from astropy.time import Time
    from earth_rotation import planning_earth_rotation
    times = np.array([value.timestamp() for value in frame.Time])
    site = EarthLocation.from_geodetic(settings.longitude_deg * u.deg, settings.latitude_deg * u.deg, settings.height_m * u.m)
    with planning_earth_rotation():
        epochs = Time(times, format='unix')
        solar = get_sun(epochs).transform_to(AltAz(obstime=epochs, location=site, pressure=0 * u.hPa)).alt.deg
    frame['_Sun altitude'] = solar
    result = []
    for a, b, x, y in zip(times[:-1], times[1:], solar[:-1], solar[1:]):
        cuts = [a, b]
        if x != y and 0 < (threshold - x) / (y - x) < 1:
            cuts.insert(1, a + (b - a) * (threshold - x) / (y - x))
        for start, end in zip(cuts[:-1], cuts[1:]):
            if np.interp((start + end) / 2, [a, b], [x, y]) <= threshold:
                result.append(SimpleNamespace(start=datetime.fromtimestamp(start, timezone.utc), end=datetime.fromtimestamp(end, timezone.utc)))
    return result


def choose_session(frame, nights, profile, settings, target, exposure, rules, moon_data=None, cloud_data=None, selection=None):
    """Choose a feasible window using configurable relative preference weights."""
    def unavailable(message):
        return dict(points=[], message=message)
    if not rules['enabled']:
        return unavailable('Imaging-session planning is disabled.')
    e = rules['exposure']
    if e['enabled'] and not e['min_seconds'] <= exposure <= e['max_seconds']:
        return unavailable('The selected exposure is outside the configured planning limits.')
    from selection_scoring import load_selection_settings, validate_selection_settings, weighted_candidates
    selection = load_selection_settings() if selection is None else validate_selection_settings(selection)
    margin = rules['visibility']['horizon_clearance_margin'] if selection['modes']['horizon'] == 'mandatory' else 0
    adjusted = np.array(profile, dtype=float, copy=True) if profile is not None else np.array([[0., 0.], [180., 0.]])
    adjusted[:, 1] += margin
    minimum = max(settings.minimum_altitude_deg, rules['visibility']['absolute_min_altitude']) if selection['modes']['altitude'] == 'mandatory' else 0.
    from horizon import horizon_altitudes
    frame = frame.copy()
    frame['_Horizon altitude'] = horizon_altitudes(np.asarray(profile), frame['Azimuth (°)']) if profile is not None else 0.
    windows = usable_windows(frame, minimum, adjusted, darkness_windows(frame, nights, settings, rules, selection))
    if not windows:
        return unavailable('No window meets the altitude, horizon-clearance and darkness settings.')
    selected_filter, dualband = filter_choice(target)
    cloud_data, moon_data = cloud_data or {}, moon_data or {}
    transit = next_transits([target], frame.Time.iloc[0].to_pydatetime(), settings.longitude_deg)[0].timestamp()
    candidates, error = weighted_candidates(windows, frame, settings, target, exposure, rules,
                                            moon_data, cloud_data, selection, transit, dualband, exposure_budget)
    if not candidates:
        return unavailable(error or 'No window satisfies the mandatory rules and fits the exposure overheads. Mandatory rules: ' + ', '.join(key for key, mode in selection['modes'].items() if mode == 'mandatory'))
    if selection['session_type'] == 'non_automated':
        best = max(candidates, key=lambda candidate: (round(candidate['selection_score'] or 0, 8), -candidate['points'][0], candidate['exposure_count']))
    else:
        best = max(candidates, key=lambda candidate: (round(candidate['selection_score'] or 0, 8), candidate['exposure_count'], -candidate['points'][0]))
    best['filter_type'] = selected_filter
    best['selection_settings'] = selection
    score_text = f"Selected by relative preferences: {best['selection_score']:.1f}/100" if best['selection_score'] is not None else 'Selected by mandatory rules; no relative rating'
    notes = [score_text + '; ' + ('transit included.' if best['transit_included'] else 'transit outside the selected window.')]
    if best['missing_cloud']:
        notes.append('Cloud forecast is incomplete or unavailable.')
    if best['missing_rain']:
        notes.append('Precipitation forecast is incomplete or unavailable.')
    if not moon_data.get('enabled') and rules['moon']['enabled']:
        notes.append('Moon assessment is unavailable.')
    if best['factors'].get('moon', 1) < 1 and rules['moon']['enabled']:
        notes.append('Moon influence is a weighted penalty, not an automatic exclusion.')
    if not best['sufficient']:
        notes.append('The available integration is below the configured minimum preference.')
    best['message'] = ' '.join(notes)
    return best
