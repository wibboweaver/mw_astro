from unittest.mock import patch
import pytest
from filter_recommendations import recommend_dualband


@pytest.mark.parametrize('kind', ['EmN','HII','PN','SNR'])
def test_emission_line_types_recommend_dualband(kind):
    with patch('filter_recommendations.catalogue_types',return_value={'TEST':kind}):
        recommended,reason=recommend_dualband('TEST')
        assert recommended and kind in reason


@pytest.mark.parametrize('kind', ['G','GPair','OCl','GCl','RfN','DrkN'])
def test_broadband_types_leave_box_clear(kind):
    with patch('filter_recommendations.catalogue_types',return_value={'TEST':kind}):
        assert recommend_dualband('TEST')[0] is False


def test_unknown_or_ambiguous_type_is_not_invented():
    with patch('filter_recommendations.catalogue_types',return_value={'TEST':'Cl+N'}):
        assert recommend_dualband('TEST')[0] is False
        assert 'unknown or ambiguous' in recommend_dualband('MISSING')[1]


def test_published_types_and_manual_catalogue_aliases():
    assert recommend_dualband('NGC 6720')[0] is True  # Ring Nebula, PN
    assert recommend_dualband('M 57')[0] is True
    assert recommend_dualband('M31')[0] is False
    assert recommend_dualband('NGC 7023')[0] is False  # Reflection nebula
