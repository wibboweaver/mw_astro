from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import numpy as np
from astropy.time import Time
from astropy.utils import iers
from earth_rotation import planning_earth_rotation, data_notice, refresh_data, current_table
from visibility import calculate_tracks
from target_table import next_transits
from targets import Target


def stale_table():
    table = current_table().copy()
    table.meta['predictive_mjd'] = Time.now().mjd - 90
    return table


def test_stale_predictions_do_not_crash_tracks_or_transits_and_settings_restore():
    table = stale_table()
    start = datetime.now(timezone.utc)
    target = Target('Horsehead', 'IC434', 85.25, -2.45)
    old_age, old_download = iers.conf.auto_max_age, iers.conf.auto_download
    with patch('earth_rotation.current_table', return_value=table):
        tracks = calculate_tracks([target], 52, -3, 0, start, 2, 10)
        assert np.isfinite(tracks['Horsehead']['Altitude (°)']).all()
        assert next_transits([target], start, -3)[0] >= start
        assert '30 days old' in data_notice(start)
    assert iers.conf.auto_max_age == old_age
    assert iers.conf.auto_download == old_download


def test_scope_restores_configuration_when_calculation_fails():
    old_age = iers.conf.auto_max_age
    try:
        with planning_earth_rotation():
            assert iers.conf.auto_max_age is None
            raise ValueError('unrelated bad input')
    except ValueError as exc:
        assert str(exc) == 'unrelated bad input'
    assert iers.conf.auto_max_age == old_age


def test_out_of_table_dates_are_identified():
    assert 'beyond' in data_notice(datetime(2100, 1, 1, tzinfo=timezone.utc))


def test_refresh_failure_preserves_local_table_and_config():
    import earth_rotation
    previous = current_table()
    age, download = iers.conf.auto_max_age, iers.conf.auto_download
    with patch.object(previous, 'copy', side_effect=OSError('offline')):
        success, message = refresh_data()
    assert not success and 'local data remain available' in message
    assert earth_rotation._table is previous
    assert iers.conf.auto_max_age == age and iers.conf.auto_download == download


def test_refresh_enables_download_only_within_refresh_scope():
    class Candidate:
        def ut1_utc(self, moment):
            assert iers.conf.auto_download is True
            assert iers.conf.auto_max_age == 30
            assert iers.conf.remote_timeout == 4
    import earth_rotation
    previous = current_table()
    old_download, old_age = iers.conf.auto_download, iers.conf.auto_max_age
    candidate = Candidate()
    try:
        with patch.object(previous, 'copy', return_value=candidate):
            success, message = refresh_data()
        assert success
        assert earth_rotation._table is candidate
        assert iers.conf.auto_download == old_download and iers.conf.auto_max_age == old_age
    finally:
        earth_rotation._table = previous


def test_startup_reuses_fresh_cache_once_without_network(monkeypatch):
    import earth_rotation
    from astropy.utils import data
    bundled = stale_table()
    fresh = bundled.copy()
    fresh.meta['predictive_mjd'] = Time.now().mjd - 1
    monkeypatch.setattr(earth_rotation, '_table', bundled)
    monkeypatch.setattr(earth_rotation, '_startup_checked', False)
    monkeypatch.setattr(data, 'cache_contents', lambda: {iers.conf.iers_auto_url: 'cached'})
    with patch.object(iers.IERS_Auto, 'read', return_value=fresh), \
            patch('astropy.utils.iers.iers.download_file', side_effect=AssertionError('network')) as download:
        stages = []
        report = lambda fraction, label: stages.append((fraction, label))
        assert earth_rotation.initialize_data(report)
        assert earth_rotation.current_table().meta['predictive_mjd'] == fresh.meta['predictive_mjd']
        assert data_notice(datetime.now(timezone.utc)) is None
        assert [fraction for fraction, _ in stages] == [0.0, 1 / 3, 2 / 3, 1.0]
        assert not earth_rotation.initialize_data(report)
        assert len(stages) == 4
        download.assert_not_called()


def test_startup_offline_keeps_local_data_and_does_not_retry(monkeypatch):
    import earth_rotation
    bundled = stale_table()
    monkeypatch.setattr(earth_rotation, '_table', bundled)
    monkeypatch.setattr(earth_rotation, '_startup_checked', False)
    monkeypatch.setattr(earth_rotation.data, 'cache_contents', lambda: {})
    with patch('astropy.utils.iers.iers.download_file', side_effect=OSError('offline')) as download:
        assert not earth_rotation.initialize_data()
        assert earth_rotation.current_table() is bundled
        assert '30 days old' in data_notice(datetime.now(timezone.utc))
        assert not earth_rotation.initialize_data()
        assert download.call_count == 1


def test_startup_updates_stale_data_and_restores_config(monkeypatch):
    import earth_rotation
    bundled = stale_table()
    fresh = bundled.copy()
    fresh.meta['predictive_mjd'] = Time.now().mjd - 1
    monkeypatch.setattr(earth_rotation, '_table', bundled)
    monkeypatch.setattr(earth_rotation, '_startup_checked', False)
    monkeypatch.setattr(earth_rotation.data, 'cache_contents', lambda: {})
    age, download, timeout = iers.conf.auto_max_age, iers.conf.auto_download, iers.conf.remote_timeout
    def update(moment):
        assert iers.conf.auto_download
        assert iers.conf.remote_timeout == 4
        fresh.ut1_utc(moment)
    from unittest.mock import Mock
    candidate = Mock(meta=fresh.meta)
    candidate.ut1_utc.side_effect = update
    with patch.object(bundled, 'copy', return_value=candidate):
        assert earth_rotation.initialize_data()
    assert earth_rotation.current_table() is candidate
    assert bundled.meta['predictive_mjd'] < fresh.meta['predictive_mjd']
    assert (iers.conf.auto_max_age, iers.conf.auto_download, iers.conf.remote_timeout) == (age, download, timeout)
