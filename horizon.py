"""Read altitude/azimuth horizon profiles and interpolate around the compass."""
from pathlib import Path
import numpy as np

LOCATION_DIR = Path(__file__).with_name("locations")


def available_horizons(directory=None):
    return sorted((directory or LOCATION_DIR).glob("*.txt"), key=lambda p: p.name.casefold())


def load_horizon(path):
    """Return sorted (azimuth, altitude) pairs from altitude-first text rows."""
    points = {}
    for line_number, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            altitude, azimuth = map(float, line.split())
        except ValueError as exc:
            raise ValueError(f"Line {line_number}: expected altitude azimuth.") from exc
        if not np.isfinite(altitude) or not -90 <= altitude <= 90:
            raise ValueError(f"Line {line_number}: altitude must be between -90 and 90°.")
        if not np.isfinite(azimuth) or not 0 <= azimuth <= 360:
            raise ValueError(f"Line {line_number}: azimuth must be between 0 and 360°.")
        azimuth %= 360
        if azimuth in points and points[azimuth] != altitude:
            raise ValueError(f"Line {line_number}: conflicting heights at azimuth {azimuth:g}°.")
        points[azimuth] = altitude
    if len(points) < 2:
        raise ValueError("A horizon needs at least two distinct azimuths.")
    return np.array(sorted(points.items()), dtype=float)


def horizon_altitudes(profile, azimuths):
    """Linear interpolation, including the wrap from the last point through north."""
    return np.interp(azimuths, profile[:, 0], profile[:, 1], period=360)
