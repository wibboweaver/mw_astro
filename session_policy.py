"""Mandatory constraints and relative preferences for automatic session selection."""
from copy import deepcopy
import math

FACTORS = ('integration', 'altitude', 'transit', 'moon', 'cloud', 'precipitation',
           'start_time', 'astronomical_night', 'horizon')
DEFAULTS = dict(integration_weight=35., altitude_weight=20., transit_weight=15.,
                moon_weight=10., cloud_weight=10., precipitation_weight=5., start_time_weight=15.,
                astronomical_night_weight=0., horizon_weight=0.,
                maximum_cloud_percent=50., unknown_condition_score=.5,
                candidate_step_minutes=10., transit_proximity_hours=2., late_start_score=.5)
DEFAULT_PARAMETERS = {
    'astronomical_night': dict(mode='mandatory'),
    'altitude': dict(mode='mandatory'),
    'horizon': dict(mode='mandatory'),
    'integration': dict(mode='relative', weight=35.),
    'transit': dict(mode='relative', weight=15.),
    'moon': dict(mode='relative', weight=10., maximum_interference=0.),
    'cloud': dict(mode='relative', weight=10., maximum_percent=50.),
    'precipitation': dict(mode='relative', weight=5., maximum_percent=0.),
    'start_time': dict(mode='relative', weight=15.),
}


def _number(value, name, low=0, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < low or high is not None and value > high:
        raise ValueError(f'{name} must be a finite number from {low}' + (f' to {high}.' if high is not None else ' upwards.'))


def validate_selection_settings(values):
    if not isinstance(values, dict) or values.keys() - (DEFAULTS.keys() | {'parameters', 'session_type', '_description'}):
        raise ValueError('Unknown or malformed session_selection settings.')
    result = DEFAULTS | {key: value for key, value in values.items() if key in DEFAULTS}
    for key, value in result.items():
        _number(value, f'session_selection.{key}')
    for key in ('unknown_condition_score', 'late_start_score'):
        _number(result[key], key, high=1)
    _number(result['maximum_cloud_percent'], 'maximum_cloud_percent', high=100)
    _number(result['candidate_step_minutes'], 'candidate_step_minutes', 5, 60)
    if not 0 < result['transit_proximity_hours'] <= 24:
        raise ValueError('transit_proximity_hours must be greater than 0 and at most 24.')
    result['session_type'] = values.get('session_type', 'non_automated')
    if result['session_type'] not in ('non_automated', 'automated'):
        raise ValueError('session_type must be non_automated or automated.')
    parameters = deepcopy(DEFAULT_PARAMETERS)
    if 'parameters' in values:
        if any(key.endswith('_weight') for key in values):
            raise ValueError('Use parameter objects, not legacy flat weights alongside parameters.')
        supplied = values['parameters']
        if not isinstance(supplied, dict) or supplied.keys() - DEFAULT_PARAMETERS.keys():
            raise ValueError('Unknown or malformed session_selection.parameters.')
        for key, definition in supplied.items():
            allowed = {'mode', 'weight', '_description'} | (DEFAULT_PARAMETERS[key].keys() - {'mode', 'weight'})
            if not isinstance(definition, dict) or definition.keys() - allowed:
                raise ValueError(f'Invalid session_selection parameter: {key}.')
            mode = definition.get('mode', parameters[key]['mode'])
            if mode not in ('mandatory', 'relative'):
                raise ValueError(f'{key}.mode must be mandatory or relative.')
            if mode == 'mandatory' and 'weight' in definition:
                raise ValueError(f'Mandatory parameter {key} cannot have a weight.')
            parameters[key].update(definition)
            if mode == 'mandatory':
                parameters[key].pop('weight', None)
            elif 'weight' not in parameters[key]:
                raise ValueError(f'Relative parameter {key} needs a weight.')
    else:
        # Explicit TOML/flat callers retain their old weighting semantics.
        for key in FACTORS:
            name = key + '_weight'
            if name in values:
                if result[name] > 0 or parameters[key]['mode'] == 'relative':
                    parameters[key].update(mode='relative', weight=result[name])
        parameters['cloud']['maximum_percent'] = result['maximum_cloud_percent']
    for key, parameter in parameters.items():
        if parameter['mode'] == 'relative':
            _number(parameter['weight'], f'{key}.weight')
        for name, maximum in (('maximum_percent', 100), ('maximum_interference', 1)):
            if name in parameter:
                _number(parameter[name], f'{key}.{name}', high=maximum)
        result[key + '_weight'] = parameter.get('weight', 0) if parameter['mode'] == 'relative' else 0
    result['modes'] = {key: parameter['mode'] for key, parameter in parameters.items()}
    result['limits'] = dict(moon=parameters['moon']['maximum_interference'],
                            cloud=parameters['cloud']['maximum_percent'],
                            precipitation=parameters['precipitation']['maximum_percent'])
    return result


def load_selection_settings(path=None):
    from configuration import read_config
    return validate_selection_settings(read_config(path).get('session_selection', {}))


def config_document(previous):
    """Migrate numeric preferences into documented rule objects for JSON."""
    parameters = deepcopy(DEFAULT_PARAMETERS)
    for key in ('integration', 'transit', 'moon', 'cloud', 'precipitation', 'start_time'):
        parameters[key]['weight'] = previous.get(key + '_weight', parameters[key]['weight'])
    parameters['cloud']['maximum_percent'] = previous.get('maximum_cloud_percent', 50)
    descriptions = {
        'astronomical_night': 'Sun at/below -18 degrees when mandatory. Relative mode rates night above astronomical twilight, down to planning_rules.darkness.maximum_sun_altitude.',
        'altitude': 'Mandatory: at/above chart.minimum_altitude_deg and the absolute planning minimum. Relative: higher average altitude earns preference.',
        'horizon': 'Actual horizon obstruction always excludes capture. Mandatory: also require planning_rules.visibility.horizon_clearance_margin. Relative: score that clearance margin.',
        'integration': 'Mandatory: meet planning_rules.integration.minimum_minutes and minimum_exposures. Relative: compare complete exposure counts after overheads.',
        'transit': 'Mandatory: include the target transit. Relative: favour windows containing or close to transit.',
        'moon': 'Mandatory: complete Moon data and effective interference no greater than maximum_interference (0 means none). Relative: average Moon penalty, adjusted for dual-band sensitivity.',
        'cloud': 'Mandatory: complete cloud data and no point above maximum_percent. Relative: decreasing preference above cloud_forecast.clear_max_percent; missing data remains unknown.',
        'precipitation': 'Mandatory: complete forecast and no probability above maximum_percent. Relative: prefer lower precipitation probability.',
        'start_time': 'Non-automated relative mode progressively favours earlier eligible dark time, with additional late/early-hours penalties. Automated sessions ignore this relative preference. Mandatory: start within the normal hours in planning_rules.timing.',
    }
    for key, parameter in parameters.items():
        parameter['_description'] = descriptions[key]
    result = dict(_description='Mandatory parameters have no weight or rating: every condition must pass, including data availability. Relative parameters contribute normalised weights; 0 disables a preference. Missing relative data uses unknown_condition_score. All-mandatory selection has no numeric rating.',
                  session_type='non_automated', parameters=parameters)
    for key in ('unknown_condition_score', 'candidate_step_minutes', 'transit_proximity_hours', 'late_start_score'):
        result[key] = previous.get(key, DEFAULTS[key])
    return result
