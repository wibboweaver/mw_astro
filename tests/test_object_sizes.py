from unittest.mock import patch
import pytest
from object_sizes import format_size, normalise_id, object_size_label


@pytest.mark.parametrize('major,minor,expected', [
    (120,60,'2 × 1°'), (60,None,'1°'), (18,10,'18 × 10′'),
    (0.5,0.25,'30 × 15″'), (1,None,'1′'),
    (None,None,'Unavailable'), (float('nan'),1,'Unavailable'),
])
def test_size_units_and_missing_dimensions(major, minor, expected):
    assert format_size(major,minor) == expected


def test_manual_identifiers_match_catalogue_sizes():
    assert normalise_id('NGC  07023') == normalise_id('NGC7023')
    assert object_size_label('NGC 7023') == object_size_label('NGC7023') != 'Unavailable'
    assert object_size_label('M 31') == object_size_label('NGC0224') != 'Unavailable'
    assert object_size_label('not in the catalogue') == 'Unavailable'


@pytest.mark.parametrize('dimensions,threshold,status',[
    ((18,6),15,'Pass'),((17.99,6),15,'Fail'),((18,6),16,'Fail'),
    ((18,None),15,'Unknown'),((None,None),15,'Unknown')])
def test_full_frame_footprint_threshold_and_pixels(monkeypatch,dimensions,threshold,status):
    import object_sizes
    monkeypatch.setattr(object_sizes,'catalogue_sizes',lambda:{'TEST':dimensions})
    result=object_sizes.frame_metrics('TEST',(2,1),(6000,4000),threshold)
    assert result['status']==status
    if dimensions==(18,6):
        assert result['coverage']=='15.0% × 10.0%'
        assert result['pixels']=='900 × 400'
    if dimensions==(18,None):assert result['pixels']=='900 × —'
    assert object_sizes.frame_metrics('MISSING',(2,1),(6000,4000))['status']=='Unknown'


def test_full_frame_estimates_scale_with_equipment(monkeypatch):
    import object_sizes
    monkeypatch.setattr(object_sizes,'catalogue_sizes',lambda:{'TEST':(180,30)})
    result=object_sizes.frame_metrics('TEST',(2,1),(6000,4000))
    assert result['oversized']
    assert result['coverage']=='150.0% × 50.0%'
    assert result['pixels']=='9,000 × 2,000'
    assert object_sizes.frame_metrics('TEST',(4,2),(6000,4000))['pixels']=='4,500 × 1,000'
