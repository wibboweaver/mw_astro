from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest
from altitude import calculate_altitudes
from targets import Target
from visibility import calculate_tracks, filter_tracks, visible_mask


def frame(alts, azs=None):
    return pd.DataFrame({'Altitude (°)': alts, 'Azimuth (°)': azs if azs is not None else [0]*len(alts)})


def test_constraints_must_hold_at_the_same_time():
    profile = np.array([[0, 60], [180, 0]])
    tracks = {'disjoint': frame([50, 20], [0, 180]), 'clear': frame([50, 50], [0, 180])}
    assert filter_tracks(tracks, 30, profile) == ['clear']


def test_window_modes_and_boundary_rules():
    tracks = {'rising': frame([20, 40]), 'setting': frame([40, 20]), 'all': frame([30, 40])}
    assert filter_tracks(tracks, 30) == ['rising', 'setting', 'all']
    assert filter_tracks(tracks, 30, mode='At start') == ['setting', 'all']
    assert filter_tracks(tracks, 30, mode='Throughout window') == ['all']
    assert not visible_mask(frame([0]), 0)[0]
    assert not visible_mask(frame([30]), 30, np.array([[0, 30], [180, 30]]))[0]


def test_horizon_wrap_and_invalid_samples():
    profile = np.array([[10, 30], [350, 10]])
    assert visible_mask(frame([21, 19], [0, 360]), 0, profile).tolist() == [True, False]
    assert not visible_mask(frame([float('nan')]), 0)[0]
    assert filter_tracks({'empty': frame([])}, 30) == []
    with pytest.raises(ValueError):
        filter_tracks({}, 30, mode='bad')


def test_batch_matches_existing_calculation_and_uses_exact_start():
    start = datetime(2026, 10, 21, 20, 30, tzinfo=timezone.utc)
    targets = (Target('Fixture A', 'A', 315.403, 68.163), Target('Fixture B', 'B', 10, 40))
    tracks = calculate_tracks(targets, 52, -3, 0, start, 12, 10)
    times, alts, azs = calculate_altitudes(315.403, 68.163, 52, -3, 0, start, 12, 10, include_azimuth=True)
    np.testing.assert_allclose(tracks['Fixture A']['Altitude (°)'], alts)
    np.testing.assert_allclose(tracks['Fixture A']['Azimuth (°)'], azs)
    assert tracks['Fixture A']['Time'].iloc[0] == start
    assert len(tracks['Fixture A']) == len(times)


def test_100_targets_and_empty_catalogue():
    start = datetime(2026, 10, 21, tzinfo=timezone.utc)
    targets = tuple(Target(f'Fixture {i}', str(i), i*3, 30) for i in range(100))
    tracks = calculate_tracks(targets, 52, -3, 0, start, 12, 10)
    assert len(tracks) == 100
    assert all(len(track) == 73 for track in tracks.values())
    assert calculate_tracks((), 52, -3, 0, start, 12, 10) == {}


def test_discovery_tests_all_candidates_before_limiting():
    from unittest.mock import patch
    from visibility import discover_tracks
    targets = tuple(Target(f'Fixture {i:03}', str(i), 10, 30) for i in range(300))
    def tracks(batch, *args):
        return {t.common_name: frame([40 + int(t.object_id)/10]*2) for t in batch}
    with patch('visibility.calculate_tracks', side_effect=tracks) as calculate:
        result = discover_tracks(targets, 52, -3, 0, datetime(2026,10,21,tzinfo=timezone.utc),12,10,30,limit=100)
    assert len(result) == 100
    assert list(result)[0] == 'Fixture 299'
    assert 'Fixture 000' not in result
    assert calculate.call_count == 2
