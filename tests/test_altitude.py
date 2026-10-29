from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from astropy.time import Time
import astropy.units as u
from astropy.utils import iers

from altitude import calculate_altitudes


def test_equatorial_target_transits_near_zenith():
    start = datetime(2026, 10, 21, 0, tzinfo=timezone.utc)
    with iers.conf.set_temp("auto_download", False):
        ra = Time(start).sidereal_time("mean", longitude=0 * u.deg).deg
    _, altitudes = calculate_altitudes(ra, 0, 0, 0, 0, start, 12, 60)
    assert altitudes[0] > 89
    assert altitudes[-1] < -88
    assert np.all(np.isfinite(altitudes))


def test_polar_target_remains_high_at_northern_site():
    _, altitudes = calculate_altitudes(0, 90, 52, 0, 0, datetime(2026, 10, 21, tzinfo=timezone.utc))
    assert np.allclose(altitudes, 52, atol=0.3)


def test_sampling_uses_elapsed_time_across_dst_and_includes_endpoint():
    start = datetime(2026, 10, 25, 0, tzinfo=ZoneInfo("Europe/London"))
    times, _ = calculate_altitudes(0, 0, 0, 0, 0, start, 3, 60)
    assert len(times) == 4
    assert (times[-1] - times[0]).total_seconds() == 10800
    assert times[0].hour == 23


@pytest.mark.parametrize("kwargs", [
    {"start": datetime(2026, 10, 21)}, {"latitude_deg": 91},
    {"duration_hours": 0}, {"step_minutes": 0}, {"ra_deg": float("nan")},
])
def test_invalid_inputs(kwargs):
    args = dict(ra_deg=0, dec_deg=0, latitude_deg=0, longitude_deg=0,
                height_m=0, start=datetime(2026, 10, 21, tzinfo=timezone.utc))
    args.update(kwargs)
    with pytest.raises(ValueError):
        calculate_altitudes(**args)


def test_azimuth_output_matches_sample_times():
    times, altitudes, azimuths = calculate_altitudes(
        315.403, 68.163, 52, -3, 0,
        datetime(2026, 10, 21, tzinfo=timezone.utc), include_azimuth=True,
    )
    assert len(times) == len(altitudes) == len(azimuths)
    assert np.all((azimuths >= 0) & (azimuths < 360))
