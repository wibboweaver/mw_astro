"""Browser-side chart and metric-style readouts; pointer motion needs no rerun."""
import json
from pathlib import Path

import pandas as pd


def chart_html(frame, minimum_altitude_deg, timezone, object_size="Unavailable", exposure_seconds=180.0, target_key="", night_periods=()):
    import math
    if not math.isfinite(exposure_seconds) or exposure_seconds <= 0:
        raise ValueError("Exposure must be positive and finite.")
    times = pd.to_datetime(frame["Time"], utc=True)
    payload = {
        "times": [int(t.timestamp() * 1000) for t in times],
        "alt": frame["Altitude (°)"].tolist(),
        "az": frame["Azimuth (°)"].tolist(),
        "horizon": frame["Horizon (°)"].tolist() if "Horizon (°)" in frame else None,
        "minimum": float(minimum_altitude_deg), "timezone": timezone,
        "object_size": object_size, "exposure_seconds": float(exposure_seconds),
        "target_key": target_key,
        "astronomical_night": [[int(interval.start.timestamp()*1000), int(interval.end.timestamp()*1000)] for interval in night_periods],
    }
    # Escape HTML-significant characters, including user-controlled timezone text.
    encoded = json.dumps(payload, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = Path(__file__).with_name("chart_template.html").read_text()
    logic = Path(__file__).with_name("observation.js").read_text()
    return template.replace("__OBSERVATION_JS__", logic).replace("__CHART_DATA__", encoded)
