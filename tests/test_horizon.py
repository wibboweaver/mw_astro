from pathlib import Path
import numpy as np
import pytest
from horizon import load_horizon, horizon_altitudes, available_horizons


def test_altitude_first_sorted_with_comments(tmp_path):
    path = tmp_path / "Garden.txt"
    path.write_text("# profile\n58 210\n\n41 128 # tree\n52 160\n")
    profile = load_horizon(path)
    np.testing.assert_allclose(profile, [[128, 41], [160, 52], [210, 58]])
    np.testing.assert_allclose(horizon_altitudes(profile, [128, 144, 185, 210]), [41, 46.5, 55, 58])


def test_interpolation_wraps_through_north(tmp_path):
    path = tmp_path / "Garden.txt"
    path.write_text("10 350\n30 10\n")
    np.testing.assert_allclose(horizon_altitudes(load_horizon(path), [350, 0, 360, 10]), [10, 20, 20, 30])


@pytest.mark.parametrize("text", ["", "41 128", "abc 90\n20 180", "10 20 30", "91 0\n20 180", "10 -1\n20 180", "nan 0\n20 180", "10 0\n20 360", "10 inf\n20 180"])
def test_invalid_profiles(tmp_path, text):
    path = tmp_path / "bad.txt"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_horizon(path)


def test_location_discovery(tmp_path):
    (tmp_path / "Garden.txt").write_text("10 0\n20 180")
    (tmp_path / "README.md").write_text("Instructions")
    assert [p.name for p in available_horizons(tmp_path)] == ["Garden.txt"]
