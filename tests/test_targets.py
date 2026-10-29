import pytest
from targets import Target, parse_targets, resolve_targets


def test_common_names_and_optional_coordinates():
    targets = parse_targets('common_name,object_id,ra_deg,dec_deg\nFixture target,TEST-ID,15.5,-20\nOther fixture,OTHER,,\n')
    assert targets == (Target('Fixture target', 'TEST-ID', 15.5, -20), Target('Other fixture', 'OTHER'))


@pytest.mark.parametrize('body', [
    'name,id\na,b', 'common_name,object_id\n,ID',
    'common_name,object_id\nName,ID\nname,OTHER',
    'common_name,object_id,ra_deg,dec_deg\na,id,10,',
    'common_name,object_id,ra_deg,dec_deg\na,id,nan,0',
    'common_name,object_id,ra_deg,dec_deg\na,id,360,0',
    'common_name,object_id,ra_deg,dec_deg\na,id,10,91',
])
def test_invalid_catalogue(body):
    with pytest.raises(ValueError):
        parse_targets(body)


def test_accept_100_reject_101_without_truncation():
    rows = ['common_name,object_id'] + [f'Fixture {i},ID{i}' for i in range(101)]
    assert len(parse_targets('\n'.join(rows[:101]))) == 100
    with pytest.raises(ValueError, match='100'):
        parse_targets('\n'.join(rows))


def test_resolution_preserves_names_skips_supplied_coordinates_and_reports_errors():
    calls = []
    def resolver(identifier):
        calls.append(identifier)
        if identifier == 'BAD':
            raise ValueError('not found')
        return {'ra_deg': 10, 'dec_deg': 20, 'name': 'canonical ID'}
    resolved, failures = resolve_targets((Target('Resolved fixture', 'GOOD'), Target('Offline fixture', 'LOCAL', 30, 40), Target('Missing fixture', 'BAD')), resolver)
    assert calls == ['GOOD', 'BAD']
    assert resolved[0].common_name == 'Resolved fixture'
    assert len(resolved) == 2 and len(failures) == 1
