"""Browser-side chart and metric-style readouts; pointer motion needs no rerun."""
import json
from pathlib import Path

import pandas as pd


def chart_html(frame, minimum_altitude_deg, timezone, object_size="Unavailable", exposure_seconds=180.0, target_key="", night_periods=(), moon_intervals=(), cloud_forecast=None):
    import math
    if not math.isfinite(exposure_seconds) or exposure_seconds <= 0:
        raise ValueError("Exposure must be positive and finite.")
    times = pd.to_datetime(frame["Time"], utc=True)
    payload = {
        "times": [int(t.timestamp() * 1000) for t in times],
        "alt": frame["Altitude (°)"].tolist(),
        "az": frame["Azimuth (°)"].tolist(),
        "cloud_forecast": cloud_forecast,
        "moon_interference": list(moon_intervals),
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


from functools import lru_cache


@lru_cache(maxsize=1)
def chart_component():
    from streamlit.components.v2 import component
    return component('observation_chart',
        html='<iframe title="Target altitude chart" style="width:100%;height:765px;border:0" sandbox="allow-scripts allow-same-origin"></iframe>',
        js=Path(__file__).with_name('chart_bridge.js').read_text())


def render_chart(content, key):
    return chart_component()(data={'html':content}, key=key, default={'interval': []}, on_interval_change=lambda: None)


def selected_interval(value, first, last):
    """Validate browser timestamps and return ordered, aware UTC endpoints."""
    import math
    from datetime import datetime, timezone
    points = value.get('interval', []) if isinstance(value, dict) else []
    if not isinstance(points, list) or len(points) > 2:
        raise ValueError('Invalid chart interval. Clear the interval and click again.')
    for point in points:
        if isinstance(point, bool) or not isinstance(point, (float, int)) or not math.isfinite(point) or not first.timestamp()*1000 <= point <= last.timestamp()*1000:
            raise ValueError('Chart interval is outside the current chart. Select it again.')
    if not points:
        raise ValueError('Missing start and stop times. Click twice on the chart to select an interval.')
    if len(points) == 1:
        raise ValueError('Missing stop time. Click a second point on the chart.')
    begin, end = sorted(points)
    if begin == end:
        raise ValueError('Start and stop times must be different. Select a nonzero interval on the chart.')
    return tuple(datetime.fromtimestamp(point/1000, timezone.utc) for point in (begin,end))


_loaded_source_stamp = (Path(__file__).stat().st_mtime_ns, Path(__file__).with_name('chart_bridge.js').stat().st_mtime_ns)
