import pandas as pd
from charts import altitude_chart


def test_threshold_is_horizontal_dotted_line_at_selected_altitude():
    frame = pd.DataFrame({"Time": pd.to_datetime(["2026-10-21T18:00Z"]), "Altitude (°)": [45]})
    spec = altitude_chart(frame, 35).to_dict()
    rule = spec["layer"][1]
    assert rule["mark"]["type"] == "rule"
    assert rule["mark"]["strokeDash"] == [2, 4]
    assert rule["encoding"]["y"]["field"] == "Minimum altitude"
    assert spec["datasets"][rule["data"]["name"]] == [{"Minimum altitude": 35}]
    assert spec["layer"][0]["encoding"]["x"]["scale"]["type"] == "utc"


def test_hover_tracks_nearest_time_and_displays_marker():
    frame = pd.DataFrame({"Time": pd.to_datetime(["2026-10-21T18:00Z", "2026-10-21T19:00Z"]), "Altitude (°)": [45, 50]})
    spec = altitude_chart(frame, 30).to_dict()
    selection = spec["params"][0]
    assert selection["name"] == "altitude_hover"
    assert selection["select"]["nearest"] is True
    assert selection["select"]["fields"] == ["Sample"]
    assert selection["select"]["on"] == "pointermove"
    marker = spec["layer"][-1]
    assert marker["mark"]["type"] == "point"
    assert marker["mark"]["filled"] is True
    assert marker["transform"][0]["filter"]["param"] == "altitude_hover"
    assert [item["field"] for item in marker["encoding"]["tooltip"]] == ["UTC time", "Altitude (°)"]


def test_hover_time_is_hours_and_minutes_only():
    frame = pd.DataFrame({"Time": pd.to_datetime(["2026-10-21T18:20Z"]), "Altitude (°)": [45]})
    spec = altitude_chart(frame, 30).to_dict()
    data = spec["datasets"][spec["layer"][0]["data"]["name"]]
    assert data[0]["UTC time"] == "18:20"
    assert "vconcat" not in spec


def test_custom_horizon_overlay_preserves_hover_readout():
    frame = pd.DataFrame({"Time": pd.to_datetime(["2026-10-21T18:00Z"]), "Altitude (°)": [45], "Azimuth (°)": [128], "Horizon (°)": [41]})
    spec = altitude_chart(frame, 30).to_dict()
    horizon = spec["layer"][2]
    assert horizon["encoding"]["y"]["field"] == "Horizon (°)"
    assert horizon["mark"]["color"] == "#c44e52"
    assert spec["layer"][-1]["transform"][0]["filter"]["param"] == "altitude_hover"


def test_selected_sample_readout():
    from charts import selected_row
    frame = pd.DataFrame({"Altitude (°)": [10, 20], "Azimuth (°)": [100, 120]})
    assert selected_row(frame, [{"Sample": 1}])["Azimuth (°)"] == 120
    assert selected_row(frame, []) is None
    assert selected_row(frame, [{"Sample": 99}]) is None
    assert selected_row(frame, [{"Sample": 0.5}]) is None
