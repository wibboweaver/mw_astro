"""Configurable, explainable preference scoring for feasible imaging windows."""
from datetime import datetime
import math
from zoneinfo import ZoneInfo

import numpy as np


from session_policy import DEFAULTS, FACTORS, load_selection_settings, validate_selection_settings


def _at(blocks, stamp):
    return next((block.get('percent') for block in blocks if block['start'] <= stamp < block['end']), None)


def weighted_candidates(windows, frame, settings, target, exposure, rules, moon_data, cloud_data,
                        selection, transit, dualband, budget):
    """Score all contiguous candidate windows without categorical Moon priority.

    Score = sum(normalised weight * factor). Integration is relative to the
    maximum feasible capture count, not capped at the preferred integration goal.
    """
    weather_enabled = rules['weather']['enabled'] and cloud_data.get('settings', {}).get('enabled', True)
    moon_enabled = rules['moon']['enabled']
    moon_known = moon_enabled and moon_data.get('enabled', False)
    cloud_blocks = cloud_data.get('segments', []) if weather_enabled else []
    rain_blocks = cloud_data.get('precipitation_segments', []) if weather_enabled else []
    moon_blocks = moon_data.get('intervals', []) if moon_known else []
    preferred_cloud = cloud_data.get('settings', {}).get('clear_max_percent', rules['weather']['preferred_max_cloud_percent'])
    modes = selection['modes']
    mandatory = [key for key in FACTORS if modes[key] == 'mandatory']
    weights = {key: selection[key + '_weight'] for key in FACTORS if modes[key] == 'relative'}
    if modes['moon'] == 'mandatory' and not moon_known:
        return [], 'Mandatory Moon rule cannot be verified: Moon data are unavailable or disabled.'
    if any(modes[key] == 'mandatory' for key in ('cloud', 'precipitation')) and not weather_enabled:
        return [], 'Mandatory weather rule cannot be verified: forecasts are disabled.'
    if not moon_enabled and 'moon' in weights:
        weights['moon'] = 0
    if not weather_enabled:
        for key in ('cloud', 'precipitation'):
            if key in weights:
                weights[key] = 0
    if selection['session_type'] == 'automated' and 'start_time' in weights:
        weights['start_time'] = 0
    total_weight = sum(weights.values())
    weights = {key: value / total_weight for key, value in weights.items()} if total_weight else {}
    unknown = selection['unknown_condition_score']
    times = np.array([stamp.timestamp() for stamp in frame.Time])
    altitudes = frame['Altitude (°)'].to_numpy(dtype=float)
    altitude_min = max(settings.minimum_altitude_deg, rules['visibility']['absolute_min_altitude']) if rules['visibility']['enabled'] else settings.minimum_altitude_deg
    altitude_span = max(1., float(np.max(altitudes)) - altitude_min)
    horizons = frame['_Horizon altitude'].to_numpy(dtype=float)
    solar = frame['_Sun altitude'].to_numpy(dtype=float) if '_Sun altitude' in frame else None
    earliest = min(first for first, last in windows)
    start_span = max(1., max(last for first, last in windows) - earliest)
    zone = ZoneInfo(settings.timezone)
    boundaries = [point / 1000 for block in cloud_blocks + rain_blocks + moon_blocks for point in (block['start'], block['end'])]
    candidates = []
    for first, last in windows:
        # Mandatory constraints remove segments; relative conditions never veto them.
        splits = sorted({first, last} | {point for point in boundaries if first < point < last})
        runs = []
        for a, b in zip(splits[:-1], splits[1:]):
            mid = (a + b) * 500
            cloud, rain = _at(cloud_blocks, mid), _at(rain_blocks, mid)
            if modes['cloud'] == 'mandatory' and (cloud is None or cloud > selection['limits']['cloud']):
                continue
            if modes['precipitation'] == 'mandatory' and (rain is None or rain > selection['limits']['precipitation']):
                continue
            level = next((block['level'] for block in moon_blocks if block['start'] <= mid < block['end']), None)
            interference = (1. if level == 'strong' else .5 if level else 0.)
            if dualband:
                interference *= rules['moon']['dualband_sensitivity_factor']
            if modes['moon'] == 'mandatory' and interference > selection['limits']['moon']:
                continue
            if runs and abs(runs[-1][1] - a) < .01:
                runs[-1] = (runs[-1][0], b)
            else:
                runs.append((a, b))
        for first, last in runs:
            first, last = math.ceil(first), math.floor(last)
            if last <= first:
                continue
            step = selection['candidate_step_minutes'] * 60
            # Limit grid growth for unusually long chart periods; retain exact
            # horizon, darkness, forecast, Moon and transit boundaries.
            step = max(step, (last - first) / 350)
            endpoints = {float(first), float(last)}
            endpoints.update(float(point) for point in np.arange(first, last, step))
            endpoints.update(point for point in boundaries if first < point < last)
            if first < transit < last:
                endpoints.add(transit)
            endpoints = np.array(sorted({float(math.ceil(point)) for point in endpoints if first <= point <= last}))
            sample = np.array(sorted(set(endpoints) | {float(point) for point in times if first < point < last}))
            mids = (sample[:-1] + sample[1:]) / 2
            spans = np.diff(sample)
            factors = {key: [] for key in ('altitude', 'horizon', 'astronomical_night', 'moon', 'cloud', 'precipitation', 'missing_cloud', 'missing_rain')}
            for mid in mids:
                altitude = float(np.interp(mid, times, altitudes))
                factors['altitude'].append(float(np.clip((altitude - altitude_min) / altitude_span, 0, 1)))
                local_horizon = float(np.interp(mid, times, horizons))
                margin = rules['visibility']['horizon_clearance_margin']
                factors['horizon'].append(float(np.clip((altitude - local_horizon) / max(.01, margin), 0, 1)))
                sun_alt = float(np.interp(mid, times, solar)) if solar is not None else -18.
                twilight = rules['darkness']['maximum_sun_altitude']
                factors['astronomical_night'].append(1. if sun_alt <= -18 else float(np.clip((twilight - sun_alt) / max(.01, twilight + 18.), 0, 1)))
                cloud, rain = _at(cloud_blocks, mid * 1000), _at(rain_blocks, mid * 1000)
                factors['cloud'].append(unknown if cloud is None else 1. if cloud <= preferred_cloud else max(0., (selection['limits']['cloud'] - cloud) / max(1., selection['limits']['cloud'] - preferred_cloud)))
                factors['precipitation'].append(unknown if rain is None else 1 - rain / 100)
                factors['missing_cloud'].append(float(cloud is None and weather_enabled))
                factors['missing_rain'].append(float(rain is None and weather_enabled))
                level = next((block['level'] for block in moon_blocks if block['start'] <= mid * 1000 < block['end']), None)
                penalty = 1. if level == 'strong' else .5 if level else 0.
                if dualband:
                    penalty *= rules['moon']['dualband_sensitivity_factor']
                factors['moon'].append(max(0., 1 - penalty) if moon_known else unknown)
            prefixes = {}
            for key, values in factors.items():
                integral = np.r_[0., np.cumsum(np.asarray(values) * spans)]
                prefixes[key] = np.interp(endpoints, sample, integral)
            for i, a in enumerate(endpoints[:-1]):
                for j in range(i + 1, len(endpoints)):
                    b = endpoints[j]
                    crossing = a <= transit <= b
                    if modes['transit'] == 'mandatory' and not crossing:
                        continue
                    count, overhead = budget(b - a, exposure, rules, crossing)
                    if count < 1:
                        continue
                    values = {key: float((prefix[j] - prefix[i]) / (b - a)) for key, prefix in prefixes.items()}
                    distance = max(a - transit, transit - b, 0.)
                    values['transit'] = max(0., 1 - distance / (selection['transit_proximity_hours'] * 3600))
                    local_start = datetime.fromtimestamp(a, zone)
                    hour = local_start.hour + local_start.minute / 60
                    normal_hours = rules['timing']['early_hours_end'] <= hour < rules['timing']['late_start_hour']
                    if modes['start_time'] == 'mandatory' and not normal_hours:
                        continue
                    earlier = max(0., 1 - (a - earliest) / start_span)
                    convenience = (.25 if hour < rules['timing']['early_hours_end'] else selection['late_start_score'] if hour >= rules['timing']['late_start_hour'] else 1.)
                    values['start_time'] = earlier * convenience
                    sufficient = count >= rules['integration']['minimum_exposures'] and count * exposure >= rules['integration']['minimum_minutes'] * 60
                    if modes['integration'] == 'mandatory' and not sufficient:
                        continue
                    candidates.append(dict(mandatory_rules=mandatory, points=[round(a * 1000), round(b * 1000)], exposure_count=count,
                                           exposure_seconds=exposure, integration_seconds=count * exposure,
                                           overhead_seconds=overhead, meridian_flip=bool(crossing),
                                           sufficient=sufficient, missing_cloud=values.pop('missing_cloud') > .0001,
                                           missing_rain=values.pop('missing_rain') > .0001,
                                           factors=values, weights=weights, transit_included=bool(crossing)))
    maximum = max((candidate['exposure_count'] for candidate in candidates), default=1)
    for candidate in candidates:
        candidate['factors']['integration'] = candidate['exposure_count'] / maximum
        candidate['factors'] = {key: candidate['factors'][key] for key in weights}
        candidate['contributions'] = {key: 100 * weight * candidate['factors'][key] for key, weight in weights.items()}
        candidate['selection_score'] = sum(candidate['contributions'].values()) if weights else None
    return candidates, ''
