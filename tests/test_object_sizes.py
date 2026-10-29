from unittest.mock import patch
import pytest
from object_sizes import format_size, normalise_id, object_size_label


@pytest.mark.parametrize('major,minor,expected', [
    (120,60,'2 × 1°'), (60,None,'1°'), (18,10,'18 × 10 arcmin'),
    (0.5,0.25,'30 × 15 arcsec'), (1,None,'1 arcmin'),
    (None,None,'Unavailable'), (float('nan'),1,'Unavailable'),
])
def test_size_units_and_missing_dimensions(major, minor, expected):
    assert format_size(major,minor) == expected


def test_manual_identifiers_match_catalogue_sizes():
    assert normalise_id('NGC  07023') == normalise_id('NGC7023')
    assert object_size_label('NGC 7023') == object_size_label('NGC7023') != 'Unavailable'
    assert object_size_label('M 31') == object_size_label('NGC0224') != 'Unavailable'
    assert object_size_label('not in the catalogue') == 'Unavailable'
