from unittest.mock import patch
import pytest
from capture_guidance import capture_guidance, guidance_markdown


@pytest.mark.parametrize('identifier', ['IC 0434', 'IC434', 'B 33', 'Barnard 33', 'Horsehead Nebula'])
def test_horsehead_is_mixed_field_not_emitting_dark_dust(identifier):
    advice = capture_guidance(identifier)
    assert advice.mode == 'Both'
    assert 'absorbing dust silhouette' in advice.broadband
    assert 'Hα backdrop' in advice.dualband
    assert 'No target-specific' in advice.lines[2]


def test_reflection_target_does_not_inherit_nearby_emission_recommendation():
    assert capture_guidance('NGC 2023').mode == 'Broadband'
    assert capture_guidance('IC 434').mode == 'Both'


@pytest.mark.parametrize('identifier', ['M 16', 'NGC 6611', 'NGC 6992', 'NGC 6960'])
def test_documented_three_line_targets_have_sources_but_no_invented_ratios(identifier):
    advice = capture_guidance(identifier)
    assert advice.sources
    assert all('Documented' in line for line in advice.lines)
    assert 'proportions: not available' in guidance_markdown(identifier)


@pytest.mark.parametrize('kind,mode', [('G','Broadband'), ('RfN','Broadband'), ('DrkN','Broadband'), ('PN','Dual-band'), ('HII','Dual-band'), ('Cl+N','Needs assessment'), (None,'Needs assessment')])
def test_type_guidance_does_not_invent_specific_line_presence(kind, mode):
    with patch('filter_recommendations.catalogue_types', return_value={'CUSTOM':kind}):
        advice = capture_guidance('CUSTOM')
        assert advice.mode == mode
        assert all('Not assessed' in line for line in advice.lines)


def test_synthetic_sulphur_is_explicitly_artistic_and_real_sho_needs_new_data():
    text = guidance_markdown('IC434')
    assert 'cannot measure S II' in text
    assert 'not measured sulphur proportions' in text
    assert 'no independent detail' in text
    assert 'additional compatible S II filter' in text
    assert 'exposure-time ratios' in text
    assert 'not by itself specify short versus long exposures' in text
