"""Altitude chart construction, independent of Streamlit."""
import altair as alt
import pandas as pd


def altitude_chart(frame, minimum_altitude_deg):
    frame = frame.copy()
    frame["Sample"] = range(len(frame))
    frame["UTC time"] = pd.to_datetime(frame["Time"], utc=True).dt.strftime("%H:%M")
    target = alt.Chart(frame).mark_line().encode(
        x=alt.X("Time:T", title="Time (UTC)", scale=alt.Scale(type="utc")),
        y=alt.Y("Altitude (°):Q", title="Altitude (°)"),
        tooltip=[alt.Tooltip("UTC time:N", title="Time (UTC)"),
                 alt.Tooltip("Altitude (°):Q", format=".1f")],
    )
    threshold = alt.Chart(pd.DataFrame({"Minimum altitude": [minimum_altitude_deg]})).mark_rule(
        color="#e69520", strokeDash=[2, 4], strokeWidth=2,
    ).encode(
        y=alt.Y("Minimum altitude:Q"),
        tooltip=[alt.Tooltip("Minimum altitude:Q", title="Minimum altitude (°)")],
    )
    # Capture the nearest time across the plot, not just directly over the line.
    hover = alt.selection_point(
        name="altitude_hover", nearest=True, on="pointermove",
        fields=["Sample"], empty=False, clear=False,
    )
    hit_targets = alt.Chart(frame).mark_point(opacity=0).encode(
        x=alt.X("Time:T", scale=alt.Scale(type="utc")),
    ).add_params(hover)
    marker = target.mark_point(filled=True, size=80).transform_filter(hover)
    guide = alt.Chart(frame).mark_rule(color="gray", strokeWidth=1).encode(
        x=alt.X("Time:T", scale=alt.Scale(type="utc")),
    ).transform_filter(hover)
    plot = target + threshold + hit_targets + guide + marker
    if "Horizon (°)" in frame:
        horizon = alt.Chart(frame).mark_line(color="#c44e52", strokeWidth=2).encode(
            x=alt.X("Time:T", scale=alt.Scale(type="utc")),
            y=alt.Y("Horizon (°):Q", title="Altitude (°)"),
            tooltip=[alt.Tooltip("UTC time:N", title="Time (UTC)"),
                     alt.Tooltip("Horizon (°):Q", format=".1f")],
        )
        plot = alt.layer(target, threshold, horizon, hit_targets, guide, marker)
    return plot


def selected_row(frame, selection):
    """Map a chart-selected sample to the displayed data, without guessing a time."""
    if not selection:
        return None
    index = selection[0].get("Sample")
    if isinstance(index, bool) or not isinstance(index, (int, float)):
        return None
    if not float(index).is_integer() or not 0 <= index < len(frame):
        return None
    return frame.iloc[int(index)]
