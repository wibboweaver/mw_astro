from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from astronomical_night import NightInterval
from configuration import Settings, load_settings, save_settings_changes
from planning import DEFAULTS, Plan
from session_suggestion import choose_session, exposure_budget, parameters_for_window
from targets import Target


@pytest.fixture
def scenario(monkeypatch):
    first = datetime(2026, 11, 21, 0, tzinfo=timezone.utc)
    last = first + timedelta(hours=4)
    frame = pd.DataFrame({'Time': [first, last], 'Altitude (°)': [60., 60.], 'Azimuth (°)': [90., 180.]})
    monkeypatch.setattr('session_suggestion.next_transits', lambda *args: [last + timedelta(hours=1)])
    return frame, [NightInterval(first, last)], Settings(latitude_deg=52, longitude_deg=-3, minimum_altitude_deg=40), Target('M31', 'M31', 10, 40), deepcopy(DEFAULTS)


def choose(scenario, **kwargs):
    frame, nights, settings, target, rules = scenario
    return choose_session(frame, nights, kwargs.pop('profile', None), settings, target, kwargs.pop('exposure', 300), rules, **kwargs)


def weather(scenario, clouds=(0, 0), rain=(0, 0)):
    first = scenario[0].Time.iloc[0].timestamp() * 1000
    step = 2 * 3600 * 1000
    def blocks(values):
        return [dict(start=first + i * step, end=first + (i + 1) * step, percent=value) for i, value in enumerate(values)]
    return dict(settings=dict(enabled=True, clear_max_percent=20), segments=blocks(clouds), precipitation_segments=blocks(rain))


def test_suggestion_covers_eligible_dark_window_and_budgets_overheads(scenario):
    result = choose(scenario, cloud_data=weather(scenario), moon_data=dict(enabled=True, intervals=[]))
    assert result['points'] == [round(scenario[0].Time.iloc[0].timestamp()*1000), round(scenario[0].Time.iloc[-1].timestamp()*1000)]
    assert result['exposure_count'] == 44
    assert result['integration_seconds'] == 44 * 300
    assert result['filter_type'] == 'Broadband (no dual-band filter)'
    assert result['exposure_count'] * 300 + result['overhead_seconds'] <= 4 * 3600


def test_cloud_preference_trims_window(scenario):
    result = choose(scenario, cloud_data=weather(scenario, clouds=(80, 0)), selection={'parameters': {'cloud': {'mode': 'mandatory', 'maximum_percent': 50}}})
    assert result['points'][0] == round((scenario[0].Time.iloc[0] + timedelta(hours=2)).timestamp()*1000)
    assert result['exposure_count'] == 20


def test_moon_and_rain_preferences_choose_quieter_part(scenario):
    first = scenario[0].Time.iloc[0].timestamp()*1000
    moon = dict(enabled=True, intervals=[dict(start=first, end=first+2*3600*1000, level='strong')])
    weights = {key: 0 for key in ('integration_weight', 'altitude_weight', 'transit_weight', 'moon_weight', 'cloud_weight', 'precipitation_weight', 'start_time_weight')}
    result = choose(scenario, cloud_data=weather(scenario), moon_data=moon, selection=weights | {'moon_weight': 100})
    assert result['points'][0] == first + 2*3600*1000
    result = choose(scenario, cloud_data=weather(scenario, rain=(70, 0)), moon_data=dict(enabled=True, intervals=[]), selection=weights | {'precipitation_weight': 100})
    assert result['points'][0] == first + 2*3600*1000


def test_unknown_forecast_not_treated_as_clear_and_known_coverage_preferred(scenario):
    result = choose(scenario)
    assert result['points'] and 'Cloud forecast is incomplete' in result['message']
    assert 'Precipitation forecast is incomplete' in result['message']
    first = scenario[0].Time.iloc[0].timestamp()*1000
    from selection_scoring import FACTORS
    weights = {key + '_weight': 0 for key in FACTORS}
    result = choose(scenario, cloud_data=weather(scenario, clouds=(None, 0)), moon_data=dict(enabled=True, intervals=[]), selection=weights | {'cloud_weight': 100})
    assert result['points'][0] == first + 2*3600*1000


def test_no_suggestion_when_blocked_or_too_short_or_exposure_invalid(scenario):
    assert not choose(scenario, profile=[[0, 70], [180, 70]])['points']
    assert not choose(scenario, cloud_data=weather(scenario, clouds=(90, 90)), selection={'parameters': {'cloud': {'mode': 'mandatory', 'maximum_percent': 50}}})['points']
    assert not choose(scenario, exposure=1000)['points']
    frame, nights, settings, target, rules = scenario
    short = frame.copy()
    short.loc[1, 'Time'] = short.Time.iloc[0] + timedelta(minutes=5)
    result = choose_session(short, nights, None, settings, target, 300, rules)
    assert not result['points'] and 'overheads' in result['message']


def test_threshold_crossings_and_horizon_margin(scenario):
    frame = scenario[0]
    frame.loc[:, 'Altitude (°)'] = [20, 60]
    result = choose(scenario)
    assert result['points'][0] == round((frame.Time.iloc[0]+timedelta(hours=2)).timestamp()*1000)
    assert not choose(scenario, profile=[[0, 59], [180, 59]])['points']


def test_filter_uses_target_guidance_without_consuming_rig_inventory(scenario, monkeypatch):
    monkeypatch.setattr('session_suggestion.capture_guidance', lambda target: SimpleNamespace(mode='Dual-band'))
    assert choose(scenario)['filter_type'] == 'Hα/O III dual-band'
    monkeypatch.setattr('session_suggestion.capture_guidance', lambda target: SimpleNamespace(mode='Needs assessment'))
    assert choose(scenario)['filter_type'].startswith('Needs assessment')


def test_flip_allowance_and_budget_boundary(scenario, monkeypatch):
    frame, _, settings, target, rules = scenario
    start, end = frame.Time.iloc[0].to_pydatetime(), frame.Time.iloc[-1].to_pydatetime()
    baseline = parameters_for_window(Plan('M31', start, end, 300), target, settings, rules)
    monkeypatch.setattr('session_suggestion.next_transits', lambda *args: [start+timedelta(hours=2)])
    result = parameters_for_window(Plan('M31', start, end, 300), target, settings, rules)
    assert result['meridian_flip'] and result['exposure_count'] < baseline['exposure_count']
    rules['exposure']['enabled'] = False
    assert exposure_budget(3600, 300, rules) == (12, 0)


def test_rig_section_is_storage_only_and_preserved_by_sidebar_updates(tmp_path):
    path = tmp_path/'config.toml'
    path.write_text('[chart]\nexposure_seconds=300\n[rig]\nmount="ZWO AM5N Harmonic Mount"\nfilter="Altair Ha OIII dualband 4nm filter"\n')
    before = load_settings(path)
    save_settings_changes(path, exposure_seconds=180)
    assert load_settings(path).exposure_seconds == 180
    assert before.focal_length_mm == 550
    assert 'filter="Altair Ha OIII dualband 4nm filter"' in path.read_text()
    assert not hasattr(before, 'mount')


def transit_scenario(monkeypatch):
    first = datetime(2026, 11, 19, 21, tzinfo=timezone.utc)
    transit = first + timedelta(hours=3)
    last = first + timedelta(hours=6, minutes=52)
    moonset = first + timedelta(hours=5, minutes=6)
    frame = pd.DataFrame({'Time': [first, transit, last], 'Altitude (°)': [50., 74., 50.], 'Azimuth (°)': [100., 180., 260.]})
    monkeypatch.setattr('session_suggestion.next_transits', lambda *args: [transit])
    settings = Settings(latitude_deg=52.293232, longitude_deg=-3.036226, minimum_altitude_deg=50)
    moon = dict(enabled=True, intervals=[dict(start=first.timestamp()*1000, end=moonset.timestamp()*1000, level='strong')])
    return frame, [NightInterval(first, last)], settings, Target('Broadband target', 'M31', 80., 36.), deepcopy(DEFAULTS), moon, transit, moonset


def test_default_weights_keep_long_transit_window_instead_of_waiting_until_2am(monkeypatch):
    frame, nights, settings, target, rules, moon, transit, _ = transit_scenario(monkeypatch)
    result = choose_session(frame, nights, None, settings, target, 300, rules, moon)
    assert result['points'][0] == round(frame.Time.iloc[0].timestamp()*1000)
    assert result['points'][0] < transit.timestamp()*1000 < result['points'][1]
    assert result['transit_included']
    assert result['factors']['moon'] < 1
    assert sum(result['weights'].values()) == pytest.approx(1)
    assert sum(result['contributions'].values()) == pytest.approx(result['selection_score'])
    assert 'transit included' in result['message']


def test_high_moon_weight_can_deliberately_choose_the_post_moonset_window(monkeypatch):
    from selection_scoring import FACTORS
    frame, nights, settings, target, rules, moon, _, moonset = transit_scenario(monkeypatch)
    weights = {key + '_weight': 0 for key in FACTORS} | {'moon_weight': 100}
    result = choose_session(frame, nights, None, settings, target, 300, rules, moon, selection=weights)
    assert result['points'][0] == round(moonset.timestamp()*1000)
    assert not result['transit_included']
    assert result['selection_score'] == pytest.approx(100)


def test_altitude_weight_favours_a_shorter_high_altitude_window(monkeypatch):
    from selection_scoring import FACTORS
    frame, nights, settings, target, rules, moon, transit, _ = transit_scenario(monkeypatch)
    weights = {key + '_weight': 0 for key in FACTORS} | {'altitude_weight': 100}
    result = choose_session(frame, nights, None, settings, target, 300, rules, moon, selection=weights)
    assert result['points'][1] - result['points'][0] < 2 * 3600 * 1000
    midpoint = sum(result['points']) / 2
    assert abs(midpoint - transit.timestamp()*1000) < 30 * 60 * 1000
    assert result['exposure_count'] >= 1


def test_scaling_weights_preserves_selection_and_zero_disables_a_preference(scenario):
    from selection_scoring import DEFAULTS, FACTORS
    first = choose(scenario, selection=DEFAULTS)
    scaled = DEFAULTS | {key + '_weight': DEFAULTS[key + '_weight'] * 10 for key in FACTORS}
    second = choose(scenario, selection=scaled)
    assert first['points'] == second['points']
    assert first['selection_score'] == pytest.approx(second['selection_score'])
    weights = {key + '_weight': 0 for key in FACTORS} | {'integration_weight': 1}
    result = choose(scenario, selection=weights)
    assert result['weights']['moon'] == 0 and result['weights']['integration'] == 1


@pytest.mark.parametrize('values', [
    {'moon_weight': -1}, {'moon_weight': True}, {'moon_weight': float('nan')},
    {'unknown_condition_score': 2}, {'transit_proximity_hours': 0},
    {'candidate_step_minutes': 1}, {'maximum_cloud_percent': 101}, {'typo_weight': 5},
])
def test_selection_config_rejects_invalid_values(values):
    from selection_scoring import validate_selection_settings
    with pytest.raises(ValueError):
        validate_selection_settings(values)


def test_weight_config_loads_and_survives_existing_settings_writes(tmp_path):
    from selection_scoring import load_selection_settings, validate_selection_settings, FACTORS
    path = tmp_path/'config.toml'
    path.write_text('[chart]\nexposure_seconds=300\n[session_selection]\nmoon_weight=60\ntransit_weight=25\n')
    assert load_selection_settings(path)['moon_weight'] == 60
    save_settings_changes(path, exposure_seconds=240)
    assert load_selection_settings(path)['transit_weight'] == 25
    policy = validate_selection_settings({key + '_weight': 0 for key in FACTORS})
    assert all(policy[key + '_weight'] == 0 for key in FACTORS)
