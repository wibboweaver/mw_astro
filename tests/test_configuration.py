import pytest
from configuration import Settings, load_settings


def test_empty_config_leaves_location_unset(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("")
    settings = load_settings(path)
    assert settings.latitude_deg is None
    assert settings.longitude_deg is None


def test_custom_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[observatory]\nlatitude_deg = 52.0\nlongitude_deg = -1.0\ntimezone = "Europe/London"\n[chart]\nstep_minutes = 5\n')
    assert load_settings(path) == Settings(latitude_deg=52, longitude_deg=-1, step_minutes=5)


@pytest.mark.parametrize("kwargs", [{"latitude_deg": 91}, {"longitude_deg": -181}, {"start_hour": 24}, {"step_minutes": 0}, {"height_m": float("nan")}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


@pytest.mark.parametrize("value", [-1, 91, float("nan")])
def test_invalid_minimum_altitude(value):
    with pytest.raises(ValueError):
        Settings(minimum_altitude_deg=value)


def test_config_minimum_altitude(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[chart]\nminimum_altitude_deg = 40\n")
    assert load_settings(path).minimum_altitude_deg == 40


def test_default_minimum_altitude_is_40():
    assert Settings().minimum_altitude_deg == 40


def test_sidebar_settings_round_trip_without_losing_non_sidebar_values(tmp_path):
    from configuration import save_settings_changes
    path = tmp_path/'config.toml'
    path.write_text('# Keep this comment\n[observatory]\nheight_m = 123.0\ntimezone = "Europe/London"\n[chart]\nduration_hours = 7\nstep_minutes = 5\n[extra]\nnote = "untouched"\n')
    saved = save_settings_changes(path, latitude_deg=52.1, longitude_deg=-3.2, horizon_file='Garden.txt',
        evening_date='2026-10-22', start_hour=20, start_minute=35, minimum_altitude_deg=45,
        visibility_mode='Throughout window', target_source='Custom CSV', catalogue_scope='All deep-sky objects',
        show_preview=False, image_field='2°')
    assert load_settings(path) == saved
    assert saved.height_m == 123 and saved.duration_hours == 7 and saved.step_minutes == 5
    assert '# Keep this comment' in path.read_text()
    assert '[extra]\nnote = "untouched"' in path.read_text()


def test_changes_merge_latest_file_and_can_clear_location(tmp_path):
    from configuration import save_settings_changes
    path = tmp_path/'config.toml'
    path.write_text('[observatory]\nlatitude_deg=52.0\n')
    save_settings_changes(path, minimum_altitude_deg=50)
    save_settings_changes(path, start_hour=22, start_minute=15)
    save_settings_changes(path, latitude_deg=None)
    saved = load_settings(path)
    assert saved.latitude_deg is None
    assert saved.minimum_altitude_deg == 50 and saved.start_minute == 15


def test_failed_atomic_replace_leaves_original_config_intact(tmp_path, monkeypatch):
    import configuration
    path = tmp_path/'config.toml'
    original = '[chart]\nminimum_altitude_deg=40\n'
    path.write_text(original)
    def fail(*args):
        raise PermissionError('read only')
    monkeypatch.setattr(configuration.os, 'replace', fail)
    with pytest.raises(PermissionError):
        configuration.save_settings_changes(path, minimum_altitude_deg=50)
    assert path.read_text() == original
    assert not list(tmp_path.glob('.config.toml.*'))


@pytest.mark.parametrize('kwargs', [{'start_minute':60}, {'evening_date':'bad'}, {'visibility_mode':'bad'},
    {'target_source':'bad'}, {'image_field':'bad'}, {'show_preview':'false'}, {'horizon_file':'../file.txt'}])
def test_invalid_persisted_sidebar_values(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_valid_upload_is_retained_for_next_session(tmp_path):
    from configuration import save_uploaded_catalogue
    path = tmp_path/'config.toml'
    path.write_text('')
    saved = save_uploaded_catalogue(b'common_name,object_id\nFixture,TEST\n', path)
    assert saved.catalogue_file == 'catalogues/last_upload.csv'
    assert (tmp_path/saved.catalogue_file).read_text() == 'common_name,object_id\nFixture,TEST\n'
    assert load_settings(path).catalogue_file == saved.catalogue_file


@pytest.mark.parametrize('value',[0,-1,float('nan'),float('inf')])
def test_invalid_exposure(value):
    with pytest.raises(ValueError):
        Settings(exposure_seconds=value)


def test_exposure_persistence(tmp_path):
    from configuration import save_settings_changes
    path=tmp_path/'config.toml'
    path.write_text('')
    save_settings_changes(path,exposure_seconds=240)
    assert load_settings(path).exposure_seconds == 240
