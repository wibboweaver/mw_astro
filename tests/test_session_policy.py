from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pandas as pd
import pytest

from astronomical_night import NightInterval
from configuration import read_config, load_settings, save_settings_changes
from planning import DEFAULTS as PLANNING_DEFAULTS
from session_policy import DEFAULT_PARAMETERS, config_document, validate_selection_settings
from session_suggestion import choose_session
from targets import Target


@pytest.fixture
def scenario(monkeypatch):
    start = datetime(2026, 11, 19, 19, tzinfo=timezone.utc)
    end = start + timedelta(hours=4)
    frame = pd.DataFrame({'Time': [start, end], 'Altitude (°)': [60., 60.], 'Azimuth (°)': [100., 200.]})
    monkeypatch.setattr('session_suggestion.next_transits', lambda *args: [start + timedelta(hours=2)])
    settings = load_settings()
    from dataclasses import replace
    settings = replace(settings, minimum_altitude_deg=40, latitude_deg=52, longitude_deg=-3)
    return frame, [NightInterval(start, end)], settings, Target('Broadband target', 'M31', 10, 40), deepcopy(PLANNING_DEFAULTS)


def weather(scenario, cloud=0, rain=0):
    first, last = [round(stamp.timestamp()*1000) for stamp in scenario[0].Time]
    return dict(settings=dict(enabled=True, clear_max_percent=20),
                segments=[dict(start=first, end=last, percent=cloud)],
                precipitation_segments=[dict(start=first, end=last, percent=rain)])


def choose(scenario, policy, **kwargs):
    frame, nights, settings, target, rules = scenario
    return choose_session(frame, nights, kwargs.pop('profile', None), settings, target, 300, rules,
                          kwargs.pop('moon_data', dict(enabled=True, intervals=[])),
                          kwargs.pop('cloud_data', weather(scenario)), selection=policy, **kwargs)


def test_mandatory_rules_have_no_weight_or_numeric_contribution(scenario):
    result = choose(scenario, {'parameters': {}})
    assert {'astronomical_night', 'altitude', 'horizon'} <= set(result['mandatory_rules'])
    for key in result['mandatory_rules']:
        assert key not in result['weights'] and key not in result['contributions'] and key not in result['factors']


def test_all_mandatory_rules_can_select_without_a_rating(scenario):
    params = {key: {'mode': 'mandatory'} for key in DEFAULT_PARAMETERS}
    result = choose(scenario, {'parameters': params})
    assert result['points']
    assert result['selection_score'] is None
    assert result['weights'] == result['contributions'] == result['factors'] == {}
    assert 'no relative rating' in result['message']


@pytest.mark.parametrize('rule,extra', [('cloud', {'maximum_percent': 20}),
                                        ('precipitation', {'maximum_percent': 0}),
                                        ('moon', {'maximum_interference': 0})])
def test_unknown_data_never_satisfies_mandatory_rule(scenario, rule, extra):
    policy = {'parameters': {rule: {'mode': 'mandatory', **extra}}}
    result = choose(scenario, policy, cloud_data={}, moon_data={})
    assert not result['points']
    assert 'Mandatory' in result['message'] or 'mandatory' in result['message']


def test_mandatory_transit_cannot_be_overridden_by_moon_weight(scenario):
    frame = scenario[0]
    first = frame.Time.iloc[0].timestamp()*1000
    transit = first + 2*3600*1000
    moon = dict(enabled=True, intervals=[dict(start=first, end=transit+30*60000, level='strong')])
    params = deepcopy(DEFAULT_PARAMETERS)
    for value in params.values():
        if value['mode'] == 'relative':
            value['weight'] = 0
    params['moon']['weight'] = 1000000
    params['transit'] = dict(mode='mandatory')
    result = choose(scenario, {'parameters': params}, moon_data=moon)
    assert result['points'][0] <= transit <= result['points'][1]
    assert 'transit' not in result['weights']


def test_mandatory_altitude_and_relative_altitude_have_distinct_semantics(scenario):
    scenario[0].loc[:, 'Altitude (°)'] = [20., 60.]
    mandatory = choose(scenario, {'parameters': {}})
    first = scenario[0].Time.iloc[0].timestamp()*1000
    assert mandatory['points'][0] >= first + 2*3600*1000
    params = deepcopy(DEFAULT_PARAMETERS)
    for value in params.values():
        if value['mode'] == 'relative':
            value['weight'] = 0
    params['integration']['weight'] = 100
    params['altitude'] = dict(mode='relative', weight=0)
    relative = choose(scenario, {'parameters': params})
    assert relative['points'][0] == first


def test_relative_horizon_margin_never_allows_actual_obstruction(scenario):
    assert not choose(scenario, {'parameters': {}}, profile=[[0, 59], [180, 59]])['points']
    policy = {'parameters': {'horizon': {'mode': 'relative', 'weight': 0}}}
    assert choose(scenario, policy, profile=[[0, 59], [180, 59]])['points']
    assert not choose(scenario, policy, profile=[[0, 61], [180, 61]])['points']


def test_mandatory_integration_rejects_short_session_instead_of_falling_back(scenario):
    frame, _, settings, target, rules = scenario
    end = frame.Time.iloc[0] + timedelta(minutes=30)
    frame.loc[1, 'Time'] = end
    nights = [NightInterval(frame.Time.iloc[0].to_pydatetime(), end.to_pydatetime())]
    policy = {'parameters': {'integration': {'mode': 'mandatory'}}}
    result = choose_session(frame, nights, None, settings, target, 300, rules, selection=policy)
    assert not result['points']
    assert 'integration' in result['message']


def test_nonautomated_sessions_prefer_earlier_dark_time_over_later_moon_free_start(scenario):
    first = scenario[0].Time.iloc[0].timestamp()*1000
    middle = first + 2*3600*1000
    moon = dict(enabled=True, intervals=[dict(start=first, end=middle, level='possible')])
    params = deepcopy(DEFAULT_PARAMETERS)
    for value in params.values():
        if value['mode'] == 'relative':
            value['weight'] = 0
    params['start_time']['weight'] = params['moon']['weight'] = 50
    human = choose(scenario, {'parameters': params, 'session_type': 'non_automated'}, moon_data=moon)
    automatic = choose(scenario, {'parameters': params, 'session_type': 'automated'}, moon_data=moon)
    assert human['points'][0] == first
    assert automatic['points'][0] == middle
    assert automatic['weights']['start_time'] == 0


def test_astronomical_night_is_mandatory_even_if_advisory_check_disabled(scenario):
    frame, _, settings, target, rules = scenario
    rules['darkness']['enabled'] = False
    result = choose_session(frame, [], None, settings, target, 300, rules, selection={'parameters': {}})
    assert not result['points']


@pytest.mark.parametrize('parameter', [
    {'moon': {'mode': 'mandatory', 'weight': 10}},
    {'horizon': {'mode': 'relative'}},
    {'cloud': {'mode': 'optional', 'weight': 10}},
    {'moon': {'mode': 'mandatory', 'maximum_interference': 2}},
])
def test_bad_parameter_modes_weights_and_thresholds_rejected(parameter):
    with pytest.raises(ValueError):
        validate_selection_settings({'parameters': parameter})


def test_json_config_updates_preserve_inventory_rules_and_other_sessions(tmp_path):
    document = {'observatory': {'latitude_deg': 52, 'longitude_deg': -3},
                'chart': {'exposure_seconds': 300}, 'rig': {'mount': 'AM5N'},
                'session_selection': config_document({}), '_notes': ['Keep these notes'],
                'planning_rules': {'exposure': {'initial_setup_minutes': 5}},
                'cloud_forecast': {'clear_max_percent': 10}, 'night_rating': {'moon_weight': 50}}
    path = tmp_path/'config.json'
    path.write_text(json.dumps(document))
    save_settings_changes(path, exposure_seconds=240)
    save_settings_changes(path, latitude_deg=None)
    stored = read_config(path)
    assert stored['rig'] == document['rig'] and stored['_notes'] == document['_notes']
    assert stored['session_selection'] == document['session_selection']
    assert load_settings(path).latitude_deg is None and load_settings(path).exposure_seconds == 240
    from planning import load_rules
    from cloud_forecast import load_cloud_settings
    from night_rating import load_rating_settings
    assert load_rules(path)['exposure']['initial_setup_minutes'] == 5
    assert load_cloud_settings(path)['clear_max_percent'] == 10
    assert load_rating_settings(path)['moon_weight'] == 50


def test_failed_json_write_keeps_complete_original(tmp_path, monkeypatch):
    import configuration
    path = tmp_path/'config.json'
    original = json.dumps({'chart': {'exposure_seconds': 300}, 'rig': {'mount': 'AM5N'}})
    path.write_text(original)
    def fail(*args):
        raise PermissionError('read only')
    monkeypatch.setattr(configuration.os, 'replace', fail)
    with pytest.raises(PermissionError):
        save_settings_changes(path, exposure_seconds=240)
    assert path.read_text() == original


@pytest.mark.parametrize('content', ['[]', '{"chart": NaN}', '{broken'])
def test_invalid_json_is_rejected(tmp_path, content):
    path = tmp_path/'config.json'
    path.write_text(content)
    with pytest.raises(ValueError):
        read_config(path)


def test_mandatory_start_time_rejects_early_hours_session(scenario):
    frame, _, settings, target, rules = scenario
    start = datetime(2026, 11, 20, 2, tzinfo=timezone.utc)
    end = start + timedelta(hours=3)
    frame.loc[:, 'Time'] = [start, end]
    nights = [NightInterval(start, end)]
    result = choose_session(frame, nights, None, settings, target, 300, rules,
                            selection={'parameters': {'start_time': {'mode': 'mandatory'}}})
    assert not result['points'] and 'start_time' in result['message']


def test_relative_night_can_use_twilight_without_a_mandatory_night_window(scenario):
    frame, _, settings, target, rules = scenario
    start = datetime(2026, 11, 19, 17, tzinfo=timezone.utc)
    end = start + timedelta(hours=3)
    frame.loc[:, 'Time'] = [start, end]
    nights = [NightInterval(start + timedelta(hours=2), end)]
    params = deepcopy(DEFAULT_PARAMETERS)
    for value in params.values():
        if value['mode'] == 'relative':
            value['weight'] = 0
    params['integration']['weight'] = 100
    params['astronomical_night'] = dict(mode='relative', weight=0)
    relative = choose_session(frame, nights, None, settings, target, 300, rules,
                              selection={'parameters': params})
    assert relative['points']
    assert relative['points'][0] < nights[0].start.timestamp()*1000
    assert 'astronomical_night' not in relative['mandatory_rules']


def test_all_mandatory_report_names_rules_without_a_numeric_rating(scenario):
    from planning import Plan, Report
    from planning_report import markdown_report
    frame, _, settings, target, _ = scenario
    parameters = {key: {'mode': 'mandatory'} for key in DEFAULT_PARAMETERS}
    result = choose(scenario, {'parameters': parameters})
    start, end = [datetime.fromtimestamp(point/1000, timezone.utc) for point in result['points']]
    text = markdown_report(Plan(target.common_name, start, end, 300), target, settings,
                           Report([], result['exposure_count'], result['integration_seconds']/60),
                           suggested_parameters=result)
    assert 'Mandatory rules passed (not rated)' in text
    assert 'no relative rating' in text
    assert 'Relative selection weights used:' not in text
