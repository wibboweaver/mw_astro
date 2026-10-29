import csv
from catalogue import read_openngc, load_catalogue


def test_real_catalogue_contains_published_names_and_coordinates():
    targets = load_catalogue()
    assert len(targets) > 100
    names = {t.object_id: t.common_name for t in targets}
    assert names['NGC7023'] == 'Iris Nebula (NGC7023)'
    assert names['NGC0224'] == 'Andromeda Galaxy (NGC0224)'
    assert len(set(t.common_name for t in targets)) == len(targets)
    assert all(0 <= t.ra_deg < 360 and -90 <= t.dec_deg <= 90 for t in targets)
    assert len(load_catalogue(False)) > 10000


def test_missing_common_name_uses_identifier_and_skips_duplicates(tmp_path):
    path = tmp_path/'NGC.csv'
    path.write_text('Name;Type;RA;Dec;Common names;M\nTEST1;G;01:00:00;-20:30:00;;\nTEST2;Dup;01:00:00;20:00:00;;\nTEST3;G;02:00:00;10:00:00;;5\n')
    assert len(read_openngc([path])) == 1
    targets = read_openngc([path], named_only=False)
    assert len(targets) == 2
    target = next(t for t in targets if t.object_id == 'TEST1')
    assert target.common_name == 'TEST1'
    assert target.ra_deg == 15 and target.dec_deg == -20.5
